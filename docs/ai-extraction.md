# AI Extraction And Normalization

Raw `Evidence` is immutable. The extraction service reads its raw text and requests
JSON from `LLMProvider.extract_progress()`. The response must validate against the
strict `ExtractionBatch` schema before it is stored as an `EvidenceInterpretation`.

Each interpretation includes an immutable snapshot of its original evidence and source
reference, the structured activity observation, confidence, provider name, optional
model name, and complete JSON response. The normalization
service similarly validates `LLMProvider.normalize_activity()` output and stores an
append-only `ActivityNormalization` record.

Malformed JSON or schema-invalid output is retried a bounded number of times. If all
attempts fail, no interpretation or normalization record is written. The deterministic
mock provider is selected by default, so the application operates without an API key.

This phase deliberately does not match observations to schedules, create conflicts,
or reconcile status.
