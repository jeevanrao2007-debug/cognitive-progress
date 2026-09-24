# Backend

This backend currently provides:

- FastAPI application bootstrap
- typed settings
- modular workflow boundaries
- health endpoint
- PostgreSQL domain models and Alembic migration for the MVP data model
- append-only evidence records and a development seed command
- deterministic CSV/XLSX/TXT/PDF ingestion with source import status tracking
- provider-independent structured extraction and activity normalization
- L5/L6 candidate matching with semantic, contextual, and ambiguity scoring

## Database commands

After configuring PostgreSQL with the `vector` extension:

```powershell
alembic upgrade head
python -m app.database.seed_demo
```

The seed command creates one sample project, one schedule, four L5/L6 activities,
four evidence records, and an unresolved conflict. It does not execute matching or
reconciliation.

## Ingestion Inputs

- Schedules accept `.csv` and `.xlsx` files with the headers in
  `data/sample/oil_india_facility_l5_l6_schedule.csv`.
- Contractor or discipline evidence accepts `.csv` and `.xlsx` files with the
  headers in `data/sample/contractor_progress_2026-09-25.csv`.
- Daily reports accept `.txt` and text-based `.pdf` files. The deterministic MVP
  parser reads `OBSERVATION|timestamp|discipline|location|status|progress|description|confidence`
  lines and preserves each complete line as raw evidence.

No LLM extraction, semantic matching, or reconciliation happens during import.

## AI Interpretation & Provider Architecture

`ExtractionService` turns an existing raw evidence record into one or more separate,
validated `EvidenceInterpretation` records. `NormalizationService` then stores a
separate `ActivityNormalization` record. Neither service updates raw evidence.

CognitiveProgress supports both real AI providers and an offline deterministic fallback:

### 1. Offline Deterministic Mode (Default)
Run without external API keys or heavy models:
```env
AI_TEXT_PROVIDER=deterministic_mock
AI_EMBEDDING_PROVIDER=deterministic_mock
```
(You can also use `AI_TEXT_PROVIDER=stub` and `AI_EMBEDDING_PROVIDER=stub`).
- Extraction and normalization use deterministic mock models.
- Embeddings use deterministic normalized SHA-256 hash vectors.

### 2. Real AI Mode (Gemini + Sentence Transformers)
Enable real LLM interpretation and semantic vector embeddings:
```env
AI_TEXT_PROVIDER=gemini
GEMINI_API_KEY=your_actual_gemini_api_key_here
AI_TEXT_MODEL=gemini-2.5-flash

AI_EMBEDDING_PROVIDER=sentence_transformers
AI_EMBEDDING_MODEL=all-MiniLM-L6-v2
```
- **Text LLM**: Official `google-genai` SDK querying `gemini-2.5-flash` with structured JSON output. If `GEMINI_API_KEY` is missing when `AI_TEXT_PROVIDER=gemini`, the system fails fast with `AIConfigurationError` (never silently downgrading).
- **Embeddings**: Local `sentence-transformers` generating real 384-dimensional dense semantic vectors (`all-MiniLM-L6-v2`). The model is loaded lazily on the first `.embed()` invocation to keep startup times fast.
- Check runtime AI mode at `GET /api/v1/health` (`REAL_AI`, `DETERMINISTIC_DEMO`, or `HYBRID`).

## SIH26122 demonstration

`POST /api/v1/demo/reset` resets and executes the complete synthetic Planning-to-
Execution Bridge scenario. The response contains the project UUID to load in the
dashboard. It includes the PIP001 three-source conflict, an automatic update, an
ambiguous match, a no-match observation, a delayed activity, and full audit history.
The demo uses `sih26122_demo` / `deterministic-demo-v1`; it never calls an LLM.

## Activity matching

`POST /api/v1/projects/{project_id}/matches/observations/{observation_id}` creates an
append-only matching result. It returns ranked candidates with semantic, contextual,
and final scores. Results can be listed (including `?outcome=ambiguous` or
`?outcome=no_match`) for planner review. Matching never reconciles or updates activity status.

## Reconciliation

`POST /api/v1/projects/{project_id}/activities/{activity_id}/reconcile` creates an
append-only, deterministic recommendation from high-confidence matched observations.
It weighs source reliability, freshness, extraction/match confidence, agreement, and
contradictions. It records supporting and conflicting source records, creates audit and
conflict records, and routes the result according to the confidence policy.

## Planner workflow

High-confidence reconciliations update the internal prototype schedule and create a
`ScheduleUpdate` plus audit record. Conflicting or ambiguous reconciliations create a
pending planner review. Planners can approve, reject, modify, select another candidate
activity, or add a comment through `/projects/{project_id}/planner-reviews`. External
Primavera and Microsoft Project integrations are intentionally out of scope.
