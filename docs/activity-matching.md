# L5/L6 Activity Matching

The matching service maps an `EvidenceInterpretation` to ranked schedule activities;
it does not alter schedules, evidence, activity status, or reconciliation records.

Candidate retrieval uses each activity's pgvector `description_embedding` when it is
available. Otherwise the configured embedding provider supplies a deterministic local
embedding, so matching remains usable without an API key. Similarity blends embedding
cosine similarity and identifier-aware lexical overlap. Context then scores discipline,
location, equipment/line identifiers, L5/L6 level, parent activity, and reported versus
planned dates.

Every invocation creates an append-only `ObservationMatchResult` and ranked candidate
rows. `matched` is returned only above `MATCHING_HIGH_CONFIDENCE_THRESHOLD`; nearby
top candidates are `ambiguous`, weak candidates are `needs_review`, and scores below
`MATCHING_NO_MATCH_THRESHOLD` are `no_match`. The latter two are retained and exposed
through the matching API for planner review.
