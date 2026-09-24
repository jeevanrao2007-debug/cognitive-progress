# Initial Architecture Decisions

## Decision 1: Use workflow-oriented backend modules

Reason:

The product problem is a reconciliation pipeline. Organizing backend code by workflow stage reduces accidental coupling and keeps each stage testable.

## Decision 2: Keep AI behind explicit interfaces

Reason:

The product requires provider independence and traceability. Business logic must depend on contracts, not vendor SDKs.

## Decision 3: Make planner review a primary product surface

Reason:

Low-confidence and conflicting cases are expected system behavior, not failure cases. The architecture must preserve escalation paths from the start.

## Decision 4: Model stable MVP evidence and schedule facts first

Reason:

Projects, schedules, activities, source evidence, import status, review records, and
audit events are stable workflow facts. They can be modeled before extraction,
matching, and reconciliation behavior without committing to any AI provider or rule.

## Decision 5: Avoid fake processing endpoints

Reason:

This phase should stay honest. Import endpoints report persisted source status and
validation errors, while matching and reconciliation endpoints remain absent.
