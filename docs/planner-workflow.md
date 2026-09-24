# Planner Workflow

`AUTO_ACCEPT` reconciliations are applied only to the internal `Activity` record by the
prototype schedule-update service. Every update creates a `ScheduleUpdate` containing
the old state, new state, reconciliation evidence, reason, decision source, and time;
it also creates an audit event. No external scheduling product is called.

`PLANNER_REVIEW` reconciliations create a pending `PlannerReview`. The planner context
endpoint returns the current schedule state, proposed reconciliation, supporting and
conflicting evidence with timestamps, match candidates, and audit history. The planner
can approve, reject, modify, select a candidate activity, or add a comment. Every
planner action is auditable.
