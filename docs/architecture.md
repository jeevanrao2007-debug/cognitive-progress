# CognitiveProgress Architecture

## Purpose

CognitiveProgress produces a reliable, explainable, schedule-linked actual-progress dataset from three MVP inputs:

- daily progress reports in PDF/TXT
- contractor or discipline spreadsheets
- L5/L6 schedule spreadsheets

## Architectural Goals

- support the core reconciliation workflow only
- keep AI provider details outside business logic
- preserve evidence and auditability for every decision
- make planner review a normal workflow, not an exception
- allow deterministic and AI-assisted logic to coexist
- keep confidence thresholds configurable

## System Shape

The system is split into two primary applications:

- `frontend`: planner-facing dashboard and review interface
- `backend`: ingestion, processing orchestration, API, and future persistence

The backend is internally separated into workflow-oriented modules so that future implementation remains disciplined:

1. `ingestion`
2. `extraction`
3. `normalization`
4. `matching`
5. `reconciliation`
6. `evidence`
7. `schedule`
8. `analytics`
9. `audit`
10. `database`
11. `ai`

## Data Flow

Planned high-level flow:

1. A project receives input files.
2. `ingestion` validates source metadata and file references.
3. `extraction` converts source files into structured progress observations.
4. `normalization` standardizes activity phrases, units, dates, and status wording.
5. `matching` links evidence items to schedule activities using deterministic and semantic signals.
6. `evidence` stores provenance, source fragments, and supporting context.
7. `reconciliation` combines evidence, resolves conflict, and assigns confidence.
8. `audit` records how a result was produced.
9. High-confidence results become auto-acceptable candidates.
10. Low-confidence or conflicting results move into planner review.
11. `analytics` supports operational visibility and quality tracking.

## Key Boundaries

### AI Boundary

AI is treated as an infrastructure dependency, not domain logic.

- Business modules call abstract AI interfaces.
- Provider-specific SDKs belong behind the `ai` module.
- Prompts, embeddings, model identifiers, and provider credentials must not leak into reconciliation logic.

### Reconciliation Boundary

`reconciliation` does not directly parse raw files.

- It receives structured evidence.
- It produces explainable status proposals with confidence.
- It never mutates schedules silently.

### Audit Boundary

Every important decision must be reproducible enough for human review:

- which source records contributed
- which match candidates were considered
- which rules or model outputs influenced the result
- why a result was auto-accepted or escalated

## Storage Direction

The target persistence model is PostgreSQL with `pgvector`.

Planned usage:

- relational storage for projects, activities, evidence, review decisions, and audit events
- vector storage for semantic retrieval over normalized activity descriptions and related evidence

The initial MVP domain schema is now in `backend/app/database/models` and is
applied through Alembic. `pgvector` is enabled with a nullable activity-description
embedding column, but no vector indexing or vector search is used yet.

See `docs/data-model.md` for the relationships and evidence-integrity rules.

Raw evidence is append-only at the database boundary: updates and deletes are
rejected by a PostgreSQL trigger, and corrections must be represented as new
evidence records.

## API Direction

Current API scope:

- service metadata
- health check

Future API scope:

- project creation
- file registration and upload orchestration
- processing job status
- linked activity views
- evidence inspection
- planner review queues
- analytics summaries

## Frontend Direction

The frontend is organized by product area, not by generic UI patterns.

Primary sections:

- dashboard
- projects
- activities
- evidence
- reconciliation
- planner-review
- analytics

The first-class workflow priority is:

- show linked progress results
- show confidence
- show evidence
- show unresolved conflicts
- support planner review decisions

## What This Phase Does Not Do

This phase does not implement:

- file parsing
- OCR
- schedule matching
- reconciliation logic
- authentication
- deployment

That omission is intentional so the architecture stays honest.
