# Cognitive Progress Reconciliation

Reconciliation is deterministic and append-only. It reads only observations with a
high-confidence, unambiguous schedule match; it does not write to `Activity.status`.

Each observation is weighted by configured source reliability, freshness relative to
the newest relevant evidence, extraction confidence, and matching score. The engine
then measures status agreement, source diversity, progress continuity, and progress or
status contradictions. It stores supporting and conflicting evidence records with their
source names, timestamps, reported state, and computed weights.

`AUTO_ACCEPT` requires high confidence and no contradictions. Conflicting or medium
confidence results use `PLANNER_REVIEW`; insufficient evidence produces `NO_DECISION`.
The engine creates an `EvidenceConflict` for contradictory evidence and an `AuditEvent`
for every reconciliation. Explanations name the actual source records used; no LLM is
an authority for the decision.

The reconciliation endpoint is:

`POST /api/v1/projects/{project_id}/activities/{activity_id}/reconcile`

It produces a recommendation only. Applying that recommendation to a schedule activity
is deliberately outside this phase.
