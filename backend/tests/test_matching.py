from datetime import UTC, date, datetime

from app.database.models import (
    Activity,
    ActivityStatus,
    Evidence,
    EvidenceInterpretation,
    ObservationMatchOutcome,
    Project,
    SourceType,
)
from app.modules.matching.schemas import MatchThresholds
from app.modules.matching.service import MatchingService


THRESHOLDS = MatchThresholds(high_confidence=0.70, ambiguous_delta=0.08, no_match=0.45, candidate_limit=10)


def make_observation(session, description: str, location: str = "Unit 3", discipline: str = "Piping") -> EvidenceInterpretation:  # type: ignore[no-untyped-def]
    project = Project(name="Matching project")
    evidence = Evidence(
        project=project, source_type=SourceType.DAILY_REPORT, source_name="DPR.txt",
        source_timestamp=datetime(2026, 8, 28, tzinfo=UTC), raw_text=description,
        raw_reference="DPR.txt#line=1",
    )
    observation = EvidenceInterpretation(
        evidence=evidence, original_evidence=description, original_reference="DPR.txt#line=1",
        activity_description=description, discipline=discipline, location=location,
        status=ActivityStatus.COMPLETED, actual_end=date(2026, 8, 28), progress=100,
        confidence=0.9, provider_name="test", model_name="test", raw_provider_response={"observations": []},
    )
    session.add(observation)
    session.commit()
    return observation


def add_activity(session, project: Project, external_id: str, description: str, location: str = "Unit 3",
                 discipline: str = "Piping", level: int = 6) -> Activity:  # type: ignore[no-untyped-def]
    activity = Activity(project=project, external_activity_id=external_id, description=description,
        location=location, discipline=discipline, level=level, planned_start=date(2026, 8, 1),
        planned_finish=date(2026, 8, 31), status=ActivityStatus.NOT_STARTED)
    session.add(activity)
    session.commit()
    return activity


def matcher(session) -> MatchingService:  # type: ignore[no-untyped-def]
    return MatchingService(session, thresholds=THRESHOLDS)


def test_matches_exact_terminology(session) -> None:  # type: ignore[no-untyped-def]
    observation = make_observation(session, "Erect Line 24-XX completed")
    expected = add_activity(session, observation.evidence.project, "PIP001", "Erect Line 24-XX")

    result = matcher(session).match_observation(observation.observation_id)

    assert result.outcome is ObservationMatchOutcome.MATCHED
    assert result.selected_activity_id == expected.activity_id
    assert result.candidates[0].external_activity_id == "PIP001"


def test_matches_terminology_mismatch(session) -> None:  # type: ignore[no-untyped-def]
    observation = make_observation(session, "24 inch line erection completed in Unit 3")
    expected = add_activity(session, observation.evidence.project, "PIP001", "Erect Line 24-XX")
    add_activity(session, observation.evidence.project, "PIP099", "Install 8 inch utility pipe")

    result = matcher(session).match_observation(observation.observation_id)

    assert result.candidates[0].activity_id == expected.activity_id
    assert result.outcome in {ObservationMatchOutcome.MATCHED, ObservationMatchOutcome.NEEDS_REVIEW}


def test_matches_abbreviations(session) -> None:  # type: ignore[no-untyped-def]
    observation = make_observation(session, "24 in line erect complete in Unit 3")
    expected = add_activity(session, observation.evidence.project, "PIP001", "Erect Line 24-XX")

    result = matcher(session).match_observation(observation.observation_id)

    assert result.candidates[0].activity_id == expected.activity_id


def test_location_disambiguates_identical_activities(session) -> None:  # type: ignore[no-untyped-def]
    observation = make_observation(session, "24 inch line erection completed", location="Unit 3")
    expected = add_activity(session, observation.evidence.project, "PIP-U3", "Erect Line 24-XX", location="Unit 3")
    add_activity(session, observation.evidence.project, "PIP-U4", "Erect Line 24-XX", location="Unit 4")

    result = matcher(session).match_observation(observation.observation_id)

    assert result.candidates[0].activity_id == expected.activity_id
    assert not result.ambiguity_flag


def test_marks_near_equal_candidates_ambiguous(session) -> None:  # type: ignore[no-untyped-def]
    observation = make_observation(session, "24 inch line erection completed")
    add_activity(session, observation.evidence.project, "PIP-A", "Erect Line 24-XX")
    add_activity(session, observation.evidence.project, "PIP-B", "Erect Line 24-YY")

    result = matcher(session).match_observation(observation.observation_id)

    assert result.outcome is ObservationMatchOutcome.AMBIGUOUS
    assert result.ambiguity_flag
    assert result.selected_activity_id is None


def test_preserves_and_exposes_unmatched_observation(session) -> None:  # type: ignore[no-untyped-def]
    observation = make_observation(session, "Cooling tower motor alignment completed", discipline="Mechanical")
    add_activity(session, observation.evidence.project, "PIP001", "Erect Line 24-XX", discipline="Piping")

    result = matcher(session).match_observation(observation.observation_id)
    unmatched = matcher(session).list_results(observation.evidence.project_id, ObservationMatchOutcome.NO_MATCH)

    assert result.outcome is ObservationMatchOutcome.NO_MATCH
    assert result.selected_activity_id is None
    assert [item.observation_id for item in unmatched] == [observation.observation_id]
