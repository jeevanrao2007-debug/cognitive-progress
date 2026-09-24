# MVP Ingestion

The ingestion phase imports files into durable schedule and evidence records without
attempting to infer schedule links or reconcile conflicting claims.

## Inputs

| Input | Supported formats | Result |
| --- | --- | --- |
| L5/L6 schedule | CSV, XLSX | One schedule plus validated activities |
| Contractor or discipline report | CSV, XLSX | One evidence record per spreadsheet row |
| Daily report or site diary | TXT, text-based PDF | One evidence record per `OBSERVATION` line |

Every upload is copied to `INGESTION_STORAGE_PATH` before parsing. `imported_sources`
stores the original name, stored reference, status, imported-record count, and any
validation errors. A failed file remains visible as a failed import; no partial rows
from that file are committed.

## API

- `POST /api/v1/projects/{project_id}/imports/schedule` accepts `file` and `version`.
- `POST /api/v1/projects/{project_id}/imports/evidence` accepts `file` and `source_type`.
- `GET /api/v1/projects/{project_id}/imports` lists imported sources.
- `GET /api/v1/projects/{project_id}/imports/{import_id}` returns one import status.

## Sample Data

`data/sample/` contains a synthetic Unit 3 facility-expansion data set. It is not
based on live Oil India project records. It contains 12 schedule activities and 24
evidence observations across Civil, Piping, Electrical, and Instrumentation.

The Piping sources deliberately disagree about the same physical work: the daily
report says the 24-inch line erection is complete, while the site diary says erection
is ongoing and the contractor report records 80%. These rows are only imported as
evidence in this phase; no conflict record or reconciliation result is created yet.
