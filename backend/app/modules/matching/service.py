"""L5/L6 observation-to-schedule activity matching without reconciliation."""

from __future__ import annotations

import math
import re
import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.ai.interfaces import EmbeddingProvider
from app.ai.registry import get_embedding_provider
from app.core.config import get_settings
from app.database.models import (Activity, ActivityNormalization, Evidence, EvidenceInterpretation,
    ObservationMatchCandidate, ObservationMatchOutcome, ObservationMatchResult)
from app.modules.extraction.errors import AIInterpretationError
from app.modules.matching.schemas import (CandidateActivityResponse, MatchThresholds,
    ObservationMatchResponse)


_TOKEN_RE = re.compile(r"[a-z0-9]+")
_IDENTIFIER_RE = re.compile(
    r"\b(?:[a-z]{1,6}[-_]?\d+[a-z0-9-_]*|\d{1,4}(?:-[a-z0-9]+)+|\d{1,4}\s*(?:inch|in|mm|cm|m|dia|#)|line\s*[-_]?\d+[a-z0-9-_]*)\b",
    re.I,
)
_SYNONYMS = {"erection": "erect", "erecting": "erect", "installed": "install", "installation": "install", "piping": "pipe", "pipes": "pipe", "welding": "weld", "commenced": "start", "inches": "inch", "ins": "inch"}



@dataclass(frozen=True)
class RankedCandidate:
    activity: Activity
    similarity_score: float
    contextual_score: float
    final_score: float
    explanation: str


class MatchingService:
    """Ranks L5/L6 activities, retaining all candidates and non-selection outcomes."""

    def __init__(self, session: Session, embedding_provider: EmbeddingProvider | None = None,
                 thresholds: MatchThresholds | None = None) -> None:
        self.session = session
        self.embedding_provider = embedding_provider or get_embedding_provider()
        settings = get_settings()
        self.thresholds = thresholds or MatchThresholds(
            high_confidence=settings.matching_high_confidence_threshold,
            ambiguous_delta=settings.matching_ambiguous_score_delta,
            no_match=settings.matching_no_match_threshold,
            candidate_limit=settings.matching_candidate_limit,
        )
        if self.thresholds.no_match > self.thresholds.high_confidence:
            raise ValueError("no_match threshold cannot exceed high_confidence threshold.")

    def match_observation(self, observation_id: uuid.UUID) -> ObservationMatchResponse:
        observation = self.session.scalar(select(EvidenceInterpretation).where(
            EvidenceInterpretation.observation_id == observation_id).options(selectinload(EvidenceInterpretation.evidence)))
        if observation is None:
            raise AIInterpretationError("Evidence interpretation does not exist.")
        normalization = self.session.scalar(select(ActivityNormalization).where(
            ActivityNormalization.observation_id == observation.observation_id).order_by(
            ActivityNormalization.created_at.desc()))
        description = normalization.normalized_activity_description if normalization else observation.activity_description
        activities = list(self.session.scalars(select(Activity).where(
            Activity.project_id == observation.evidence.project_id).options(selectinload(Activity.parent_activity))))
        ranked = self._retrieve_and_rank(observation, description, activities, normalization)
        outcome, ambiguous = self._outcome(ranked)
        result = ObservationMatchResult(observation_id=observation.observation_id, outcome=outcome,
            ambiguity_flag=ambiguous, best_score=ranked[0].final_score if ranked else None,
            high_confidence_threshold=self.thresholds.high_confidence,
            ambiguous_score_delta=self.thresholds.ambiguous_delta, no_match_threshold=self.thresholds.no_match)
        self.session.add(result)
        self.session.flush()
        for rank, candidate in enumerate(ranked, start=1):
            self.session.add(ObservationMatchCandidate(result_id=result.result_id,
                activity_id=candidate.activity.activity_id, rank=rank, similarity_score=candidate.similarity_score,
                contextual_score=candidate.contextual_score, final_score=candidate.final_score,
                explanation=candidate.explanation))
        self.session.commit()
        return self._response(result, ranked)

    def list_results(self, project_id: uuid.UUID,
                     outcome: ObservationMatchOutcome | None = None) -> list[ObservationMatchResponse]:
        statement = (select(ObservationMatchResult).join(ObservationMatchResult.interpretation)
            .join(EvidenceInterpretation.evidence).where(Evidence.project_id == project_id)
            .options(selectinload(ObservationMatchResult.candidates).selectinload(ObservationMatchCandidate.activity))
            .order_by(ObservationMatchResult.created_at.desc()))
        if outcome is not None:
            statement = statement.where(ObservationMatchResult.outcome == outcome)
        return [self._stored_response(result) for result in self.session.scalars(statement)]

    def _normalized_description(self, observation: EvidenceInterpretation) -> str:
        normalization = self.session.scalar(select(ActivityNormalization).where(
            ActivityNormalization.observation_id == observation.observation_id).order_by(
            ActivityNormalization.created_at.desc()))
        return normalization.normalized_activity_description if normalization else observation.activity_description

    def _retrieve_and_rank(self, observation: EvidenceInterpretation, description: str,
                            activities: list[Activity],
                            normalization: ActivityNormalization | None = None) -> list[RankedCandidate]:
        observation_vector = self.embedding_provider.embed(description)
        evidence_vector: list[float] | None = None
        if (
            observation.original_evidence
            and observation.original_evidence.strip()
            and observation.original_evidence.strip().lower() != description.strip().lower()
        ):
            evidence_vector = self.embedding_provider.embed(observation.original_evidence)

        preliminary: list[tuple[Activity, float]] = []
        for activity in activities:
            vector = activity.description_embedding
            if vector is None or len(vector) != len(observation_vector):
                vector = self.embedding_provider.embed(activity.description)
                activity.description_embedding = vector

            sim = self._cosine(observation_vector, vector)
            if evidence_vector is not None:
                sim = max(sim, self._cosine(evidence_vector, vector))
            similarity = self._clamp(sim)
            preliminary.append((activity, similarity))

        preliminary.sort(key=lambda item: (-item[1], item[0].external_activity_id))
        ranked = [self._rank_candidate(observation, description, observation_vector, activity, similarity, normalization)
                  for activity, similarity in preliminary[:self.thresholds.candidate_limit]]
        return sorted(ranked, key=lambda item: (-item.final_score, item.activity.external_activity_id))

    def _rank_candidate(self, observation: EvidenceInterpretation, description: str,
                        observation_vector: list[float], activity: Activity,
                        similarity: float, normalization: ActivityNormalization | None = None) -> RankedCandidate:
        notes: list[str] = []
        scores: list[float] = []

        obs_discipline = (normalization.normalized_discipline if normalization and normalization.normalized_discipline
                          else observation.discipline)
        if obs_discipline:
            same = self._normalise(obs_discipline) == self._normalise(activity.discipline or "")
            scores.append(1.0 if same else 0.0)
            notes.append("discipline matches" if same else "discipline differs")

        obs_location = (normalization.normalized_location if normalization and normalization.normalized_location
                        else observation.location)
        location_score: float | None = None
        if obs_location and activity.location:
            loc_obs = obs_location.strip().lower()
            loc_act = activity.location.strip().lower()
            if loc_obs == loc_act:
                location_score = 1.0
            else:
                loc_tokens = set(_TOKEN_RE.findall(loc_obs))
                act_tokens = set(_TOKEN_RE.findall(loc_act))
                loc_nums = {t for t in loc_tokens if t.isdigit()}
                act_nums = {t for t in act_tokens if t.isdigit()}
                if loc_nums and act_nums and not (loc_nums & act_nums):
                    location_score = 0.0
                else:
                    location_score = len(loc_tokens & act_tokens) / len(loc_tokens | act_tokens) if loc_tokens | act_tokens else 0.0
            scores.append(location_score)
            notes.append(f"location similarity {location_score:.2f}")

        identifiers = self._identifiers(description) | self._identifiers(observation.original_evidence)
        activity_identifiers = self._identifiers(activity.description) | self._identifiers(activity.external_activity_id)
        if identifiers:
            identifier_score = 1.0 if identifiers & activity_identifiers else 0.0
            scores.append(identifier_score)
            notes.append("line/equipment identifier overlaps" if identifier_score else "no identifier overlap")

        if activity.parent_activity is not None and activity.parent_activity.description:
            parent_vec = activity.parent_activity.description_embedding
            if parent_vec is None or len(parent_vec) != len(observation_vector):
                parent_vec = self.embedding_provider.embed(activity.parent_activity.description)
                activity.parent_activity.description_embedding = parent_vec
            parent_sim = self._clamp(self._cosine(observation_vector, parent_vec))
            scores.append(parent_sim)
            notes.append(f"WBS parent similarity {parent_sim:.2f}")

        scores.append(1.0 if activity.level >= 6 else 0.55)

        if observation.actual_end or observation.actual_start:
            scores.append(self._date_score(observation.actual_end or observation.actual_start,
                                           activity.planned_start, activity.planned_finish))
            notes.append("schedule dates considered")

        contextual = sum(scores) / len(scores) if scores else 0.5
        final = 0.72 * similarity + 0.28 * contextual
        if location_score is not None:
            final -= 0.15 * (1 - location_score)
        if identifiers and activity_identifiers and not (identifiers & activity_identifiers):
            final -= 0.10
        final = self._clamp(final)
        return RankedCandidate(activity, similarity, contextual, final,
            f"semantic similarity {similarity:.2f}; contextual score {contextual:.2f}; " + "; ".join(notes))


    def _outcome(self, ranked: list[RankedCandidate]) -> tuple[ObservationMatchOutcome, bool]:
        if not ranked or ranked[0].final_score < self.thresholds.no_match:
            return ObservationMatchOutcome.NO_MATCH, False
        if len(ranked) > 1 and ranked[0].final_score - ranked[1].final_score <= self.thresholds.ambiguous_delta:
            return ObservationMatchOutcome.AMBIGUOUS, True
        if ranked[0].final_score >= self.thresholds.high_confidence:
            return ObservationMatchOutcome.MATCHED, False
        return ObservationMatchOutcome.NEEDS_REVIEW, False

    def _response(self, result: ObservationMatchResult, ranked: list[RankedCandidate]) -> ObservationMatchResponse:
        selected = ranked[0].activity.activity_id if result.outcome is ObservationMatchOutcome.MATCHED and ranked else None
        return ObservationMatchResponse(result_id=result.result_id, observation_id=result.observation_id,
            outcome=result.outcome, ambiguity_flag=result.ambiguity_flag, best_score=result.best_score,
            selected_activity_id=selected, created_at=result.created_at,
            candidates=[self._candidate_response(item, rank=rank) for rank, item in enumerate(ranked, start=1)])

    def _stored_response(self, result: ObservationMatchResult) -> ObservationMatchResponse:
        candidates = sorted(result.candidates, key=lambda item: item.rank)
        selected = candidates[0].activity_id if result.outcome is ObservationMatchOutcome.MATCHED and candidates else None
        return ObservationMatchResponse(result_id=result.result_id, observation_id=result.observation_id,
            outcome=result.outcome, ambiguity_flag=result.ambiguity_flag, best_score=result.best_score,
            selected_activity_id=selected, created_at=result.created_at,
            candidates=[CandidateActivityResponse(activity_id=item.activity_id,
                external_activity_id=item.activity.external_activity_id, description=item.activity.description,
                discipline=item.activity.discipline, location=item.activity.location, level=item.activity.level,
                similarity_score=item.similarity_score, contextual_score=item.contextual_score,
                final_score=item.final_score, explanation=item.explanation, rank=item.rank) for item in candidates])

    @staticmethod
    def _candidate_response(item: RankedCandidate, rank: int = 1) -> CandidateActivityResponse:
        activity = item.activity
        return CandidateActivityResponse(activity_id=activity.activity_id, external_activity_id=activity.external_activity_id,
            description=activity.description, discipline=activity.discipline, location=activity.location, level=activity.level,
            similarity_score=item.similarity_score, contextual_score=item.contextual_score,
            final_score=item.final_score, explanation=item.explanation, rank=rank)

    @staticmethod
    def _normalise(value: str) -> str:
        return " ".join(_SYNONYMS.get(token, token) for token in _TOKEN_RE.findall(value.lower()))


    @classmethod
    def _token_similarity(cls, left: str, right: str) -> float:
        left_tokens, right_tokens = set(cls._normalise(left).split()), set(cls._normalise(right).split())
        return len(left_tokens & right_tokens) / len(left_tokens | right_tokens) if left_tokens or right_tokens else 0.0

    @staticmethod
    def _identifiers(value: str) -> set[str]:
        raw_matches = _IDENTIFIER_RE.findall(value)
        ids = {item.lower().replace(" ", "") for item in raw_matches}
        for item in raw_matches:
            for num in re.findall(r"\d+", item):
                ids.add(num)
        return ids

    @staticmethod
    def _cosine(left: list[float], right: list[float]) -> float:
        if len(left) != len(right):
            return 0.0
        denominator = math.sqrt(sum(item * item for item in left)) * math.sqrt(sum(item * item for item in right))
        return sum(a * b for a, b in zip(left, right)) / denominator if denominator else 0.0

    @staticmethod
    def _date_score(report_date: date, planned_start: date | None, planned_finish: date | None) -> float:
        if planned_start is None and planned_finish is None:
            return 0.5
        start, finish = planned_start or planned_finish, planned_finish or planned_start
        if start <= report_date <= finish:
            return 1.0
        distance = min(abs((report_date - start).days), abs((report_date - finish).days))
        return max(0.0, 1 - distance / 30)

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(1.0, value))
