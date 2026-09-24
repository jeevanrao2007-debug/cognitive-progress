# CognitiveProgress

**SIH Problem Statement**: SIH26122 — Oil India Limited  
**System**: AI-Powered Planning-to-Execution Bridge & Progress Reconciliation Platform

CognitiveProgress is an explainable, safeguarded planning-to-execution reconciliation platform developed for SIH26122 (Oil India Limited). It bridges the gap between field execution reality and enterprise project schedules by ingesting multi-source daily progress records (DPRs, contractor logs, site supervisor diaries, inspection notes) alongside baseline schedule data (CSV/XLSX). CognitiveProgress extracts structured field observations, matches them semantically to granular L5/L6 work breakdown structure (WBS) activities, reconciles multi-source discrepancies with temporal and dependency validation, and routes uncertain or conflicting progress to human planners before recording verified updates into an append-only execution memory and audit trail.

---

## Architecture

CognitiveProgress is organized into modular layers designed for clarity, deterministic safety, and enterprise reliability:

1. **React / Vite Frontend**: Modern TypeScript dashboard featuring the Reconciliation Center, Activity Explorer, Evidence Feed, Dependency Conflict Monitor, Planner Review Queue, and Audit Trail.
2. **FastAPI Backend**: Asynchronous, strictly typed Python service layer exposing clear domain endpoints under `/api/v1`.
3. **SQLAlchemy / Database Layer**: Robust persistence layer supporting zero-configuration local SQLite (`cognitiveprogress.db`) for immediate local development as well as PostgreSQL 14+ via Alembic migrations.
4. **Semantic Matching**: Hybrid matching engine combining deterministic keyword normalization with sentence-transformer embeddings to rank and match observations against L5/L6 activity definitions.
5. **Reconciliation Engine**: Multi-source reconciliation system scoring evidence freshness, source reliability weighting, and cross-source agreement/contradiction.
6. **Dependency Validation**: Execution graph precedence and temporal continuity checks that flag out-of-sequence execution or unfulfilled predecessor activities.
7. **Planner Review (Human-in-the-Loop)**: Safeguarded review queue routing ambiguous matches, contradiction conflicts, or low-confidence progress to human planners for approval, modification, or rejection.
8. **Schedule Bridge**: Append-only progress recording that maintains complete provenance and prevents silent schedule corruption.
9. **Execution Memory**: Historical memory store maintaining audit records, contractor reliability histories, and recurrence patterns over time.

---

## Main Workflow

```text
Field Evidence (DPRs, Contractor CSVs, Site Diaries)
   │
   ▼
1. Structured Extraction (Schema validation & deterministic/LLM extraction)
   │
   ▼
2. L5/L6 Semantic Matching (Embedding similarity & keyword normalization)
   │
   ▼
3. Multi-Source Reconciliation (Reliability weighting & freshness decay)
   │
   ▼
4. Conflict & Confidence Check (Dependency checks, contradiction detection)
   │
   ├─► [High Confidence & No Conflict] ──► Verified Schedule Update ──► Execution Memory
   │
   └─► [Ambiguous / Low Confidence / Conflict] ──► Planner Review (Human-in-the-loop)
                                                        │
                                                        ▼
                                                  Verified Schedule Update
```

---

## Project Structure

```text
cognitive-progress/
├── backend/                  # FastAPI backend application
│   ├── app/
│   │   ├── ai/               # AI providers (Gemini LLM & Sentence Transformers, mock fallbacks)
│   │   ├── api/              # REST API route handlers
│   │   ├── core/             # Configuration and database engine
│   │   ├── models/           # SQLAlchemy ORM models
│   │   ├── schemas/          # Pydantic schemas
│   │   └── services/         # Extraction, matching, reconciliation, schedule services
│   ├── data/imports/         # Runtime staging for uploaded evidence files
│   ├── migrations/           # Alembic database migration scripts
│   ├── tests/                # Comprehensive pytest suite (154 tests)
│   ├── .env.example          # Backend environment template
│   └── pyproject.toml        # Backend dependencies and configuration
├── frontend/                 # React 18 + Vite + TypeScript frontend
│   ├── public/               # Public assets and hero media
│   ├── src/
│   │   ├── components/       # UI components & dashboard views
│   │   ├── services/         # API client bindings
│   │   └── types/            # TypeScript interfaces
│   ├── .env.example          # Frontend environment template
│   └── package.json          # Frontend dependencies and scripts
├── data/
│   ├── demo_sih26122/        # Synthetic SIH26122 test fixtures
│   └── sample/               # Sample synthetic schedules and field reports
├── docs/                     # Technical architecture and decision records
├── run.bat                   # One-click Windows development launcher
├── stop.bat                  # One-click service shutdown utility
├── .env.example              # Root environment configuration reference
├── .gitignore                # Production-grade git ignore configuration
└── README.md                 # Project documentation
```

---

## Local Development Instructions

### Prerequisites

- **Python**: 3.11+
- **Node.js**: 18+ and **npm**

### Option A: One-Click Windows Launcher

Double-click `run.bat` or execute in terminal:

```cmd
run.bat
```

This script:
1. Detects Python and Node.js.
2. Initializes `.env` files from `.env.example` templates if missing.
3. Sets up the Python virtual environment (`backend\.venv`) and installs dependencies.
4. Installs frontend packages (`frontend\node_modules`).
5. Starts the FastAPI backend (`http://127.0.0.1:8000`).
6. Starts the Vite frontend (`http://127.0.0.1:5173`).
7. Opens the dashboard in your default browser.

To stop all running services:
```cmd
stop.bat
```

---

### Option B: Manual Setup

#### 1. Backend Setup

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
copy .env.example .env
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Backend endpoints:
- API Base: `http://127.0.0.1:8000/api/v1`
- Interactive Swagger Docs: `http://127.0.0.1:8000/docs`
- Health Check: `http://127.0.0.1:8000/api/v1/health`

#### 2. Frontend Setup

```powershell
cd frontend
copy .env.example .env
npm install
npm run dev
```

Frontend application runs at: `http://127.0.0.1:5173`

---

## Environment Variables

CognitiveProgress uses `.env.example` files as configuration templates.

> [!IMPORTANT]
> **Production credentials, real API keys, and sensitive tokens must NEVER be committed to Git.**
> All real credentials must reside solely in local `.env` files which are excluded from version control via `.gitignore`.

### Backend Configuration (`backend/.env.example`)

| Variable | Description | Default / Example |
| :--- | :--- | :--- |
| `APP_NAME` | Name of the FastAPI application | `CognitiveProgress API` |
| `APP_ENV` | Application environment (`development` / `production`) | `development` |
| `APP_DEBUG` | Enable debug logs | `true` |
| `API_V1_PREFIX` | API endpoint prefix | `/api/v1` |
| `FRONTEND_ORIGIN` | Allowed CORS origin for frontend | `http://127.0.0.1:5173` |
| `DATABASE_URL` | SQLAlchemy connection URL (leave blank for default SQLite) | `sqlite:///./cognitiveprogress.db` |
| `AI_TEXT_PROVIDER` | LLM Provider (`deterministic_mock` or `gemini`) | `deterministic_mock` |
| `GEMINI_API_KEY` | Google Gemini API Key (required only if provider is `gemini`) | *Leave blank in template* |
| `AI_TEXT_MODEL` | Gemini model name | `gemini-2.5-flash` |
| `AI_EMBEDDING_PROVIDER` | Embedding Provider (`deterministic_mock` or `sentence_transformers`) | `deterministic_mock` |
| `AI_EMBEDDING_MODEL` | Embedding model identifier | `all-MiniLM-L6-v2` |

### Frontend Configuration (`frontend/.env.example`)

| Variable | Description | Default / Example |
| :--- | :--- | :--- |
| `VITE_APP_NAME` | Name displayed in UI | `CognitiveProgress` |
| `VITE_API_BASE_URL` | Backend API base URL | `http://127.0.0.1:8000/api/v1` |

---

## Sample and Demo Data (SIH26122)

CognitiveProgress includes synthetic, realistic demonstration data designed specifically for the SIH26122 problem scenario:

- `data/demo_sih26122/`: Deterministic test fixtures for the live demonstration scenario:
  - `schedule.csv`: Baseline L5/L6 Oil India facility project schedule (Civil, Piping, Electrical, Instrumentation).
  - `contractor.csv`: Progress reported by the mechanical contractor.
  - `supervisor.txt`: Daily field log from the site supervisor.
  - `site_diary.txt`: Site diary notes with environmental and execution context.
  - `delay_cause.txt`: Identified delay causes and rain stoppage evidence.
  - `dependency_conflict.txt`: Unfulfilled predecessor execution scenario.
  - `high_confidence.txt` & `ambiguous.txt`: Test cases demonstrating high-confidence auto-updates versus ambiguous matches.
- `data/sample/`: Sample files representing external files that can be uploaded into the system:
  - `oil_india_facility_l5_l6_schedule.csv`: 20-activity facility schedule.
  - `daily_progress_report_2026-09-24.txt`: Unstructured daily progress report.
  - `contractor_progress_2026-09-25.csv`: Multi-discipline contractor progress spreadsheet.
  - `site_diary_2026-09-25.txt`: Unstructured site diary notes.

### Running the Live SIH Demonstration Scenario

You can reset the baseline and run the end-to-end multi-source reconciliation scenario with a single API call:

```powershell
curl -X POST http://127.0.0.1:8000/api/v1/demo/reset
```

Or click **"Reset Baseline"** in the frontend dashboard. This automatically ingests the schedule and multi-source evidence, triggers semantic matching, evaluates cross-source conflicts (including the three-source PIP001 discrepancy), and populates the planner review queue.

---

## Testing & Verification

The backend includes a comprehensive automated test suite (154 tests):

```powershell
cd backend
.\.venv\Scripts\activate
pytest -v
```

The frontend can be built and type-checked via:

```powershell
cd frontend
npm run build
```

---

## System Boundaries & Realistic Limitations

CognitiveProgress adheres strictly to honest engineering practices and transparent capabilities:

- **Schedule Import**: Baseline schedule integration is implemented via structured CSV/XLSX table ingestion with WBS hierarchy parsing. Direct live proprietary Primavera P6 EPPM APIs or Microsoft Project Server integrations are not currently connected.
- **Evidence Extraction**: Text and tabular parsing processes structured CSVs and natural language text logs using structured schemas with deterministic fallbacks or Google Gemini. Direct production OCR (scanned PDF image scanning) or speech-to-text (ASR voice note transcription) are future architectural modules.
- **Audit & Provenance**: All schedule modifications remain within the internal CognitiveProgress database and execution memory; no updates are pushed back to external proprietary tools without explicit export or manual planner authorization.
