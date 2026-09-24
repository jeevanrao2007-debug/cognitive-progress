# Frontend Architecture

## Purpose

The frontend is the planner-facing surface for understanding linked progress, uncertainty, and review actions.

## Structure

```text
frontend/src/
|-- app/
|-- components/
|-- features/
|   |-- dashboard/
|   |-- projects/
|   |-- activities/
|   |-- evidence/
|   |-- reconciliation/
|   `-- planner-review/
|-- services/
`-- types/
```

## Principles

- organize by product workflow
- keep feature types explicit
- isolate API access in `services`
- keep generic UI elements in `components`
- avoid mixing evidence, reconciliation, and review concerns

## Feature Intent

### `dashboard`

Entry point for system overview, workflow status, and key metrics.

### `projects`

Project-level navigation and source registration flows in later phases.

### `activities`

Linked schedule activity views and actual-progress tables in later phases.

### `evidence`

Evidence inspection UI for source-level traceability in later phases.

### `reconciliation`

System-generated decisions, confidence, and explanation views in later phases.

### `planner-review`

Manual review queue for uncertain or conflicting activity results.

### `analytics`

Quality and throughput views for reconciliation behavior over time.

## Current Scope

This phase includes only:

- layout shell
- product framing
- status placeholders
- backend connection status area

No fake data workflows are implemented.
