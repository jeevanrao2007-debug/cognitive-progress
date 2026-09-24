# Backend Module Boundaries

## `ingestion`

Owns input registration and source metadata.

Responsibilities:

- identify source type
- validate file metadata
- associate files with a project and source context

Does not:

- parse business meaning from file content

## `extraction`

Owns conversion from raw source documents to structured observations.

Responsibilities:

- parse text-bearing input
- extract dates, quantities, activities, locations, and status phrases

Does not:

- link data to the master schedule

## `normalization`

Owns standardization of extracted observations.

Responsibilities:

- normalize activity descriptions
- standardize units and status terminology
- align temporal expressions

## `matching`

Owns schedule-linking candidate generation and scoring.

Responsibilities:

- compare normalized observations to L5/L6 schedule activities
- combine deterministic and semantic signals
- produce ranked candidates

Does not:

- make the final accepted status decision

## `reconciliation`

Owns conflict handling and probable status selection.

Responsibilities:

- compare evidence from multiple sources
- decide whether confidence is sufficient for auto-accept
- route uncertain items for planner review

## `evidence`

Owns provenance and explainability artifacts.

Responsibilities:

- preserve source references
- attach snippets, rows, or cell-level references
- support UI evidence inspection

## `schedule`

Owns the schedule activity representation.

Responsibilities:

- represent L5/L6 activities
- expose schedule metadata needed by matching and reconciliation

## `analytics`

Owns metrics and visibility.

Responsibilities:

- confidence distribution
- review queue volume
- match quality trends
- source conflict rates

## `audit`

Owns decision trace history.

Responsibilities:

- store processing events
- record planner overrides
- log AI-assisted decision context

## `database`

Owns persistence infrastructure.

Responsibilities:

- engine/session lifecycle
- repositories in later phases
- schema integration in later phases

## `ai`

Owns provider abstraction.

Responsibilities:

- text generation interface
- embedding interface
- provider-neutral configuration

Does not:

- encode domain policy
- make hidden reconciliation decisions
