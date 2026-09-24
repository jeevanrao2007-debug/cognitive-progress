# MVP Data Model

The relational model keeps source facts separate from later AI-assisted decisions.

```text
Project 1---* Schedule
Project 1---* Activity (parent activity is optional)
Project 1---* Evidence
Evidence 1---* ActivityMatch *---1 Activity
Activity 1---* Reconciliation
Activity 1---* EvidenceConflict
Activity 1---* PlannerReview
AuditEvent records changes to any entity by type and identifier.
```

## Evidence Integrity

`evidence` contains the source name, timestamp, raw text and/or raw file reference,
and its extracted fields together. The original evidence row is never overwritten.
The initial PostgreSQL migration creates a trigger that rejects evidence updates and
deletes; a correction is represented by another evidence row.

## Matching And Vectors

`activity_matches` records candidate links and the component scores that produced
them. `activities.description_embedding` is nullable and uses pgvector, but no
embedding generation, vector index, or vector query is introduced in this phase.

## Decision Records

Reconciliations, conflicts, and planner reviews are separate tables. This prevents a
future reconciliation process from mutating source evidence or silently changing the
schedule. Scores and confidences are bounded by database constraints.
