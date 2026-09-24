import re
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.models import (
    Activity,
    ActivityDependency,
    ActivityStatus,
    DependencyType,
    Evidence,
    ImportedSource,
    ImportKind,
    ImportStatus,
    Project,
    Schedule,
    SourceType,
)
from app.modules.ingestion.errors import IngestionError
from app.modules.ingestion.readers import read_tabular_rows, read_text


SCHEDULE_REQUIRED_COLUMNS = {
    "external_activity_id", "discipline", "description", "location", "planned_start",
    "planned_finish", "parent_activity_id", "level", "status",
}
EVIDENCE_REQUIRED_COLUMNS = {
    "source_timestamp", "activity_description", "status", "progress", "discipline", "location",
}
OBSERVATION_PREFIX = "OBSERVATION|"


class IngestionService:
    """Imports structured source data only; it does not match or reconcile activities."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def import_schedule(
        self, project_id: uuid.UUID, source_path: Path, source_name: str, version: str
    ) -> ImportedSource:
        source = self._start_source(project_id, ImportKind.SCHEDULE, None, source_name, source_path)
        try:
            rows = read_tabular_rows(source_path)
            if not rows:
                raise IngestionError("Source contains no data rows.")

            raw_headers = set(rows[0].keys())
            norm_headers = {k.strip().lower().replace(" ", "_"): k for k in rows[0].keys()}

            schedule_attrs = {
                "planned_start", "planned_end", "planned_finish", "start", "finish", "early_start", "early_finish",
                "predecessors", "predecessor", "predecessor_id", "predecessor_activity_id", "pred",
                "wbs", "actual_start", "actual_end", "percent_complete", "progress", "%_complete",
            }
            if SCHEDULE_REQUIRED_COLUMNS.issubset(raw_headers):
                parsed_rows = [self._parse_schedule_row(row, index + 2) for index, row in enumerate(rows)]
            elif (
                any(k in norm_headers for k in ("activity_id", "activity_code", "external_activity_id", "task_id"))
                and any(k in norm_headers for k in ("activity_name", "description", "name", "activity", "task_name"))
                and any(k in norm_headers for k in schedule_attrs)
            ):
                parsed_rows = [self._parse_flexible_schedule_row(row, norm_headers, index + 2) for index, row in enumerate(rows)]
            else:
                self._validate_headers(rows, SCHEDULE_REQUIRED_COLUMNS)
                parsed_rows = [self._parse_schedule_row(row, index + 2) for index, row in enumerate(rows)]

            self._validate_schedule_rows(project_id, parsed_rows)
            schedule = Schedule(
                project_id=project_id,
                source_file=str(source_path),
                version=version,
                imported_at=datetime.now(UTC),
            )
            activities = [
                Activity(
                    project_id=project_id,
                    external_activity_id=row["external_activity_id"],
                    discipline=row["discipline"],
                    description=row["description"],
                    location=row["location"],
                    planned_start=row["planned_start"],
                    planned_finish=row["planned_finish"],
                    actual_start=row.get("actual_start"),
                    actual_end=row.get("actual_end"),
                    actual_progress=row.get("actual_progress"),
                    level=row["level"],
                    status=row["status"],
                )
                for row in parsed_rows
            ]
            activity_by_external_id = {
                activity.external_activity_id: activity for activity in activities
            }
            for row, activity in zip(parsed_rows, activities, strict=True):
                parent_external_id = row["parent_activity_id"]
                if parent_external_id and parent_external_id in activity_by_external_id:
                    activity.parent_activity = activity_by_external_id[parent_external_id]

            self.session.add(schedule)
            self.session.add_all(activities)
            self.session.flush()

            # Wire up predecessor dependencies if present
            dependencies: list[ActivityDependency] = []
            for row, activity in zip(parsed_rows, activities, strict=True):
                for pred_ext_id in row.get("predecessors", []):
                    pred_act = activity_by_external_id.get(pred_ext_id)
                    if pred_act is None:
                        pred_act = self.session.scalar(
                            select(Activity).where(
                                Activity.project_id == project_id,
                                Activity.external_activity_id == pred_ext_id,
                            )
                        )
                    if pred_act is not None:
                        dependencies.append(
                            ActivityDependency(
                                dependency_id=uuid.uuid4(),
                                project_id=project_id,
                                predecessor_id=pred_act.activity_id,
                                successor_id=activity.activity_id,
                                dependency_type=DependencyType.FINISH_TO_START,
                                lag_days=0,
                            )
                        )

            if dependencies:
                self.session.add_all(dependencies)
                self.session.flush()
            self._complete_source(source, len(activities))
            self.session.commit()
            return source
        except (IngestionError, IntegrityError) as error:
            self.session.rollback()
            return self._fail_source(source.import_id, error)

    def import_evidence(
        self,
        project_id: uuid.UUID,
        source_path: Path,
        source_name: str,
        source_type: SourceType,
        default_timestamp: datetime | None = None,
    ) -> ImportedSource:
        source = self._start_source(project_id, ImportKind.EVIDENCE, source_type, source_name, source_path)
        try:
            if source_path.suffix.lower() in {".csv", ".xlsx"}:
                evidence = self._evidence_from_tabular(project_id, source, source_path, source_type)
            else:
                evidence = self._evidence_from_text(
                    project_id, source, source_path, source_type, default_timestamp or datetime.now(UTC)
                )
            self.session.add_all(evidence)
            self._complete_source(source, len(evidence))
            self.session.commit()
            return source
        except (IngestionError, IntegrityError) as error:
            self.session.rollback()
            return self._fail_source(source.import_id, error)

    def _start_source(
        self, project_id: uuid.UUID, import_kind: ImportKind, source_type: SourceType | None,
        source_name: str, source_path: Path,
    ) -> ImportedSource:
        if self.session.get(Project, project_id) is None:
            raise IngestionError("Project does not exist.")
        clean_name = Path(source_name).name if source_name else "source"
        source = ImportedSource(
            project_id=project_id,
            import_kind=import_kind,
            source_type=source_type,
            source_name=clean_name,
            stored_reference=str(source_path),
            status=ImportStatus.PROCESSING,
        )
        self.session.add(source)
        self.session.commit()
        return source

    def _complete_source(self, source: ImportedSource, records_imported: int) -> None:
        source.status = ImportStatus.COMPLETED
        source.records_imported = records_imported
        source.completed_at = datetime.now(UTC)
        source.validation_errors = None

    def _fail_source(self, import_id: uuid.UUID, error: Exception) -> ImportedSource:
        source = self.session.get(ImportedSource, import_id)
        if source is None:
            raise error
        source.status = ImportStatus.FAILED
        source.error_message = str(error)
        source.validation_errors = getattr(error, "validation_errors", None) or None
        source.completed_at = datetime.now(UTC)
        self.session.commit()
        return source

    @staticmethod
    def _validate_headers(rows: list[dict[str, str]], required_columns: set[str]) -> None:
        if not rows:
            raise IngestionError("Source contains no data rows.")
        headers = set(rows[0])
        missing = sorted(required_columns - headers)
        if missing:
            raise IngestionError(
                "Required columns are missing.",
                [{"field": column, "message": "Required column is missing."} for column in missing],
            )

    def _validate_schedule_rows(self, project_id: uuid.UUID, rows: list[dict[str, object]]) -> None:
        external_ids = [str(row["external_activity_id"]) for row in rows]
        duplicates = sorted({value for value in external_ids if external_ids.count(value) > 1})
        known_ids = set(
            self.session.scalars(
                select(Activity.external_activity_id).where(Activity.project_id == project_id)
            )
        )
        errors = [
            {"field": "external_activity_id", "message": f"Duplicate activity ID: {value}"}
            for value in duplicates + sorted(known_ids.intersection(external_ids))
        ]
        external_id_set = set(external_ids)
        for row in rows:
            parent_id = row.get("parent_activity_id")
            if parent_id and parent_id not in external_id_set:
                if row.get("_is_flexible"):
                    row["parent_activity_id"] = None
                else:
                    errors.append({
                        "field": "parent_activity_id",
                        "message": f"Parent activity does not exist in this schedule: {parent_id}",
                    })
        if errors:
            raise IngestionError("Schedule validation failed.", errors)

    def _parse_schedule_row(self, row: dict[str, str], row_number: int) -> dict[str, object]:
        errors: list[dict[str, str]] = []
        for column in SCHEDULE_REQUIRED_COLUMNS:
            if not row.get(column, "").strip() and column != "parent_activity_id":
                errors.append({"field": column, "message": f"Row {row_number}: value is required."})
        parsed_status = self._parse_status(row.get("status", ""), row_number, errors)
        parsed_start = self._parse_date(row.get("planned_start", ""), "planned_start", row_number, errors)
        parsed_finish = self._parse_date(row.get("planned_finish", ""), "planned_finish", row_number, errors)
        parsed_act_start = self._parse_optional_date(row.get("actual_start"), "actual_start", row_number, errors)
        parsed_act_end = self._parse_optional_date(row.get("actual_end"), "actual_end", row_number, errors)
        prog_val = row.get("actual_progress") or row.get("percent_complete")
        progress = self._parse_flexible_percentage(prog_val) if prog_val else None
        try:
            level = int(row.get("level", ""))
            if level not in {5, 6}:
                raise ValueError
        except ValueError:
            errors.append({"field": "level", "message": f"Row {row_number}: level must be 5 or 6."})
            level = 6
        pred_val = None
        for key in ("predecessors", "predecessor", "predecessor_id", "predecessor_activity_id"):
            if key in row and row[key]:
                pred_val = row[key]
                break
        preds: list[str] = []
        if pred_val:
            preds = [p.strip() for p in re.split(r"[,;|]", str(pred_val)) if p.strip()]

        if errors:
            raise IngestionError("Schedule validation failed.", errors)
        return {
            "external_activity_id": row["external_activity_id"],
            "discipline": row["discipline"],
            "description": row["description"],
            "location": row["location"],
            "planned_start": parsed_start,
            "planned_finish": parsed_finish,
            "actual_start": parsed_act_start,
            "actual_end": parsed_act_end,
            "actual_progress": progress,
            "parent_activity_id": row["parent_activity_id"] or None,
            "level": level,
            "status": parsed_status,
            "predecessors": preds,
        }

    def _parse_flexible_schedule_row(
        self, row: dict[str, str], norm_headers: dict[str, str], row_number: int
    ) -> dict[str, object]:
        errors: list[dict[str, str]] = []
        act_id_key = (
            norm_headers.get("activity_id")
            or norm_headers.get("activity_code")
            or norm_headers.get("external_activity_id")
            or norm_headers.get("task_id")
            or norm_headers.get("id")
            or norm_headers.get("activity")
        )
        desc_key = (
            norm_headers.get("activity_name")
            or norm_headers.get("description")
            or norm_headers.get("name")
            or norm_headers.get("task_name")
        )
        pred_key = (
            norm_headers.get("predecessors")
            or norm_headers.get("predecessor")
            or norm_headers.get("predecessor_id")
            or norm_headers.get("predecessor_activity_id")
            or norm_headers.get("pred")
        )
        disc_key = (
            norm_headers.get("discipline")
            or norm_headers.get("trade")
            or norm_headers.get("dept")
            or norm_headers.get("department")
        )
        loc_key = (
            norm_headers.get("location")
            or norm_headers.get("area")
            or norm_headers.get("zone")
            or norm_headers.get("workfront")
        )
        start_key = (
            norm_headers.get("planned_start")
            or norm_headers.get("start")
            or norm_headers.get("early_start")
            or norm_headers.get("target_start")
        )
        finish_key = (
            norm_headers.get("planned_end")
            or norm_headers.get("planned_finish")
            or norm_headers.get("finish")
            or norm_headers.get("early_finish")
            or norm_headers.get("target_finish")
            or norm_headers.get("end")
        )
        act_start_key = norm_headers.get("actual_start") or norm_headers.get("act_start")
        act_end_key = (
            norm_headers.get("actual_end")
            or norm_headers.get("actual_finish")
            or norm_headers.get("act_finish")
            or norm_headers.get("act_end")
        )
        parent_key = (
            norm_headers.get("wbs")
            or norm_headers.get("parent_activity_id")
            or norm_headers.get("parent_id")
            or norm_headers.get("parent")
        )
        level_key = norm_headers.get("level")
        status_key = norm_headers.get("status") or norm_headers.get("activity_status")
        prog_key = (
            norm_headers.get("percent_complete")
            or norm_headers.get("progress")
            or norm_headers.get("%_complete")
            or norm_headers.get("actual_progress")
        )

        act_id = row.get(act_id_key, "").strip() if act_id_key else ""
        desc = row.get(desc_key, "").strip() if desc_key else ""
        if not act_id:
            errors.append({"field": "activity_id", "message": f"Row {row_number}: activity ID is required."})
        if not desc:
            desc = act_id

        parsed_start = self._parse_optional_date(row.get(start_key) if start_key else None, "planned_start", row_number, errors)
        parsed_finish = self._parse_optional_date(row.get(finish_key) if finish_key else None, "planned_finish", row_number, errors)
        parsed_act_start = self._parse_optional_date(row.get(act_start_key) if act_start_key else None, "actual_start", row_number, errors)
        parsed_act_end = self._parse_optional_date(row.get(act_end_key) if act_end_key else None, "actual_end", row_number, errors)

        progress = self._parse_flexible_percentage(row.get(prog_key) if prog_key else None)

        status_val = row.get(status_key, "").strip() if status_key else ""
        if status_val:
            parsed_status = self._parse_flexible_status(status_val)
        elif parsed_act_end or progress == 100.0:
            parsed_status = ActivityStatus.COMPLETED
        elif parsed_act_start or (progress is not None and progress > 0.0):
            parsed_status = ActivityStatus.IN_PROGRESS
        else:
            parsed_status = ActivityStatus.NOT_STARTED

        level = 6
        if level_key and row.get(level_key, "").strip():
            try:
                l_val = int(row.get(level_key, "").strip())
                if l_val in {5, 6}:
                    level = l_val
            except ValueError:
                pass

        preds: list[str] = []
        if pred_key and row.get(pred_key):
            preds = [p.strip() for p in re.split(r"[,;|]", str(row[pred_key])) if p.strip()]

        if errors:
            raise IngestionError("Schedule validation failed.", errors)

        discipline = row.get(disc_key, "").strip() if disc_key and row.get(disc_key) else None
        location = row.get(loc_key, "").strip() if loc_key and row.get(loc_key) else None
        parent_id = row.get(parent_key, "").strip() if parent_key and row.get(parent_key) else None

        return {
            "external_activity_id": act_id,
            "discipline": discipline or None,
            "description": desc,
            "location": location or None,
            "planned_start": parsed_start,
            "planned_finish": parsed_finish,
            "actual_start": parsed_act_start,
            "actual_end": parsed_act_end,
            "actual_progress": progress,
            "parent_activity_id": parent_id or None,
            "level": level,
            "status": parsed_status,
            "predecessors": preds,
            "_is_flexible": True,
        }

    def import_text_evidence(
        self,
        project_id: uuid.UUID,
        raw_text: str,
        source_name: str,
        source_type: SourceType,
        source_timestamp: datetime | None = None,
    ) -> tuple[ImportedSource, Evidence]:
        """Ingest natural language text or raw DPR directly without a pre-saved file."""
        source_path = Path(f"virtual://{source_name}")
        source = self._start_source(project_id, ImportKind.EVIDENCE, source_type, source_name, source_path)
        try:
            content = raw_text.strip()
            if not content:
                raise IngestionError("Field report is empty.")
            extracted_date = self._extract_header_date(content)
            timestamp = source_timestamp or extracted_date or datetime.now(UTC)
            evidence_record = Evidence(
                project_id=project_id,
                source_type=source_type,
                source_name=source_name,
                source_timestamp=timestamp,
                raw_text=content,
                raw_reference=f"{source_name}#pasted",
                extracted_activity_description=None,
                extracted_status=None,
                extracted_progress=None,
                discipline=None,
                location=None,
                extraction_confidence=None,
            )
            self.session.add(evidence_record)
            self._complete_source(source, 1)
            self.session.commit()
            return source, evidence_record
        except (IngestionError, IntegrityError) as error:
            self.session.rollback()
            return self._fail_source(source.import_id, error), None  # type: ignore[return-value]

    def _evidence_from_tabular(
        self, project_id: uuid.UUID, source: ImportedSource, path: Path, source_type: SourceType
    ) -> list[Evidence]:
        rows = read_tabular_rows(path)
        if not rows:
            raise IngestionError("Spreadsheet contains no data rows.")
        headers = set(rows[0].keys())
        if EVIDENCE_REQUIRED_COLUMNS.issubset(headers):
            return [
                self._parse_evidence_row(project_id, source, row, index + 2, source_type)
                for index, row in enumerate(rows)
            ]
        # Flexible tabular parsing for discipline or contractor progress reports
        return [
            self._parse_flexible_evidence_row(project_id, source, row, index + 2, source_type)
            for index, row in enumerate(rows)
        ]

    def _parse_flexible_evidence_row(
        self, project_id: uuid.UUID, source: ImportedSource, row: dict[str, str], row_number: int,
        source_type: SourceType,
    ) -> Evidence:
        norm = {k.lower().strip().replace(" ", "_"): v for k, v in row.items()}
        desc = (
            norm.get("activity_description") or norm.get("description") or
            norm.get("activity") or norm.get("task") or norm.get("work_performed") or
            norm.get("scope") or norm.get("item")
        )
        if not desc or not desc.strip():
            # Build raw description from all non-empty values
            non_empty = [f"{k}: {v}" for k, v in row.items() if v]
            desc = " | ".join(non_empty) if non_empty else "Field Activity"
        
        # Look for timestamp/date
        ts_val = (
            norm.get("source_timestamp") or norm.get("timestamp") or
            norm.get("date") or norm.get("report_date") or norm.get("time")
        )
        timestamp = self._parse_flexible_datetime(ts_val) if ts_val else datetime.now(UTC)

        status_val = norm.get("status") or norm.get("state") or "unknown"
        status = self._parse_flexible_status(status_val)

        prog_val = (
            norm.get("progress") or norm.get("progress_percent") or
            norm.get("percent") or norm.get("%") or norm.get("pct")
        )
        progress = self._parse_flexible_percentage(prog_val) if prog_val else (100.0 if status == ActivityStatus.COMPLETED else None)

        discipline = norm.get("discipline") or norm.get("trade") or norm.get("dept") or None
        location = norm.get("location") or norm.get("area") or norm.get("unit") or None
        raw_repr = " | ".join(f"{k}: {v}" for k, v in row.items() if v)

        return Evidence(
            project_id=project_id,
            source_type=source_type,
            source_name=source.source_name,
            source_timestamp=timestamp,
            raw_text=raw_repr,
            raw_reference=f"{source.stored_reference}#row={row_number}",
            extracted_activity_description=desc.strip(),
            extracted_status=status,
            extracted_progress=progress,
            discipline=discipline,
            location=location,
            extraction_confidence=0.90,
        )

    def _evidence_from_text(
        self, project_id: uuid.UUID, source: ImportedSource, path: Path, source_type: SourceType,
        default_timestamp: datetime,
    ) -> list[Evidence]:
        text_content = read_text(path)
        if not text_content or not text_content.strip():
            raise IngestionError("Field report is empty.")

        # Backward compatibility: Check for legacy pipe-delimited OBSERVATION| lines
        has_observation_prefix = any(
            line.strip().startswith(OBSERVATION_PREFIX) for line in text_content.splitlines()
        )
        if has_observation_prefix:
            observations: list[Evidence] = []
            for line_number, line in enumerate(text_content.splitlines(), start=1):
                clean_line = line.strip()
                if not clean_line.startswith(OBSERVATION_PREFIX):
                    continue
                fields = clean_line.split("|")
                if len(fields) != 8:
                    raise IngestionError(
                        "Text observation has an invalid field count.",
                        [{"field": "observation", "message": f"Line {line_number}: expected 8 pipe-delimited fields."}],
                    )
                _, timestamp, discipline, location, status, progress, description, confidence = fields
                observations.append(
                    self._build_evidence(
                        project_id=project_id, source=source, source_type=source_type,
                        source_timestamp=self._parse_datetime(timestamp, "source_timestamp", line_number),
                        description=description, status=self._parse_status(status, line_number, []),
                        progress=self._parse_percentage(progress, line_number), discipline=discipline,
                        location=location, confidence=self._parse_confidence(confidence, line_number),
                        raw_text=clean_line, raw_reference=f"{path}#line={line_number}",
                    )
                )
            return observations

        # Natural language field report / DPR (TXT or PDF)
        extracted_date = self._extract_header_date(text_content)
        timestamp = default_timestamp or extracted_date or datetime.now(UTC)
        return [
            Evidence(
                project_id=project_id,
                source_type=source_type,
                source_name=source.source_name,
                source_timestamp=timestamp,
                raw_text=text_content.strip(),
                raw_reference=str(path),
                extracted_activity_description=None,
                extracted_status=None,
                extracted_progress=None,
                discipline=None,
                location=None,
                extraction_confidence=None,
            )
        ]

    @staticmethod
    def _extract_header_date(text: str) -> datetime | None:
        date_match = re.search(r"\b(202\d-[01]\d-[0-3]\d)\b", text)
        if date_match:
            try:
                d = date.fromisoformat(date_match.group(1))
                return datetime(d.year, d.month, d.day, tzinfo=UTC)
            except ValueError:
                pass
        return None

    @staticmethod
    def _parse_flexible_datetime(value: str | None) -> datetime:
        if not value:
            return datetime.now(UTC)
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            pass
        date_match = re.search(r"\b(202\d-[01]\d-[0-3]\d)\b", value)
        if date_match:
            try:
                d = date.fromisoformat(date_match.group(1))
                return datetime(d.year, d.month, d.day, tzinfo=UTC)
            except ValueError:
                pass
        return datetime.now(UTC)

    @staticmethod
    def _parse_flexible_status(value: str | None) -> ActivityStatus:
        if not value:
            return ActivityStatus.UNKNOWN
        v = value.strip().lower().replace("-", "_").replace(" ", "_")
        if v in {"completed", "complete", "done", "finished"}:
            return ActivityStatus.COMPLETED
        if v in {"in_progress", "active", "started", "commenced", "underway", "progress"}:
            return ActivityStatus.IN_PROGRESS
        if v in {"not_started", "pending", "unstarted", "planned"}:
            return ActivityStatus.NOT_STARTED
        if v in {"on_hold", "hold", "suspended", "paused", "delayed"}:
            return ActivityStatus.ON_HOLD
        try:
            return ActivityStatus(v)
        except ValueError:
            return ActivityStatus.UNKNOWN

    @staticmethod
    def _parse_flexible_percentage(value: str | None) -> float | None:
        if not value:
            return None
        clean = value.strip().removesuffix("%")
        try:
            val = float(clean)
            return max(0.0, min(100.0, val))
        except ValueError:
            return None


    def _parse_evidence_row(
        self, project_id: uuid.UUID, source: ImportedSource, row: dict[str, str], row_number: int,
        source_type: SourceType,
    ) -> Evidence:
        errors: list[dict[str, str]] = []
        for column in EVIDENCE_REQUIRED_COLUMNS:
            if not row.get(column, "").strip():
                errors.append({"field": column, "message": f"Row {row_number}: value is required."})
        if errors:
            raise IngestionError("Evidence validation failed.", errors)
        return self._build_evidence(
            project_id, source, source_type,
            self._parse_datetime(row["source_timestamp"], "source_timestamp", row_number),
            row["activity_description"], self._parse_status(row["status"], row_number, errors),
            self._parse_percentage(row["progress"], row_number), row["discipline"], row["location"],
            self._parse_confidence(row.get("extraction_confidence", "0.95"), row_number),
            row.get("raw_text") or " | ".join(row.values()), f"{source.stored_reference}#row={row_number}",
        )

    @staticmethod
    def _build_evidence(
        project_id: uuid.UUID, source: ImportedSource, source_type: SourceType, source_timestamp: datetime,
        description: str, status: ActivityStatus, progress: float, discipline: str, location: str,
        confidence: float, raw_text: str, raw_reference: str,
    ) -> Evidence:
        return Evidence(
            project_id=project_id, source_type=source_type, source_name=source.source_name,
            source_timestamp=source_timestamp, raw_text=raw_text, raw_reference=raw_reference,
            extracted_activity_description=description, extracted_status=status,
            extracted_progress=progress, discipline=discipline, location=location,
            extraction_confidence=confidence,
        )

    @staticmethod
    def _parse_date(value: str, field: str, row: int, errors: list[dict[str, str]]) -> date:
        try:
            return date.fromisoformat(value)
        except ValueError:
            errors.append({"field": field, "message": f"Row {row}: expected YYYY-MM-DD."})
            return date.min

    @staticmethod
    def _try_parse_date(value: object) -> date | None:
        if not value:
            return None
        val_str = str(value).strip()
        if not val_str:
            return None
        try:
            return date.fromisoformat(val_str)
        except ValueError:
            pass
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(val_str, fmt).date()
            except ValueError:
                continue
        return None

    @classmethod
    def _parse_optional_date(cls, value: object, field: str, row: int, errors: list[dict[str, str]]) -> date | None:
        if not value:
            return None
        val_str = str(value).strip()
        if not val_str:
            return None
        d = cls._try_parse_date(val_str)
        if d is None:
            errors.append({"field": field, "message": f"Row {row}: invalid date for {field}."})
            return None
        return d

    @staticmethod
    def _parse_datetime(value: str, field: str, row: int) -> datetime:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError as error:
            raise IngestionError(
                "Evidence validation failed.",
                [{"field": field, "message": f"Row {row}: expected ISO-8601 timestamp."}],
            ) from error

    @staticmethod
    def _parse_status(value: str, row: int, errors: list[dict[str, str]]) -> ActivityStatus:
        try:
            return ActivityStatus(value.strip().lower())
        except ValueError:
            errors.append({"field": "status", "message": f"Row {row}: unsupported status '{value}'."})
            if errors:
                raise IngestionError("Validation failed.", errors)
            return ActivityStatus.UNKNOWN

    @staticmethod
    def _parse_percentage(value: str, row: int) -> float:
        try:
            percentage = float(value.strip().removesuffix("%"))
        except ValueError as error:
            raise IngestionError("Evidence validation failed.", [{"field": "progress", "message": f"Row {row}: expected 0 to 100."}]) from error
        if not 0 <= percentage <= 100:
            raise IngestionError("Evidence validation failed.", [{"field": "progress", "message": f"Row {row}: expected 0 to 100."}])
        return percentage

    @staticmethod
    def _parse_confidence(value: str, row: int) -> float:
        try:
            confidence = float(value)
        except ValueError as error:
            raise IngestionError("Evidence validation failed.", [{"field": "extraction_confidence", "message": f"Row {row}: expected 0 to 1."}]) from error
        if not 0 <= confidence <= 1:
            raise IngestionError("Evidence validation failed.", [{"field": "extraction_confidence", "message": f"Row {row}: expected 0 to 1."}])
        return confidence
