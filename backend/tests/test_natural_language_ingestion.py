"""Focused test suite for Phase 1: Real Natural-Language Field Report / DPR Ingestion."""

import io
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from pypdf import PdfWriter
from sqlalchemy import select

from app.api.routes import imports as imports_route
from app.api.routes.imports import get_session
from app.database.models import (
    Activity,
    ActivityStatus,
    Evidence,
    EvidenceInterpretation,
    ImportKind,
    ImportStatus,
    ImportedSource,
    Project,
    Reconciliation,
    SourceType,
)
from app.main import app
from app.modules.extraction.schemas import ExtractedObservation, ExtractionBatch
from app.modules.extraction.service import ExtractionService
from app.modules.ingestion.errors import IngestionError
from app.modules.ingestion.service import IngestionService
from app.modules.matching.service import MatchingService
from app.modules.normalization.service import NormalizationService
from app.modules.reconciliation.service import ReconciliationService
from app.ai.mock_provider import DeterministicEmbeddingProvider, DeterministicMockProvider


def create_test_project(session) -> Project:
    project = Project(name=f"Phase 1 Ingestion Test Project {uuid.uuid4().hex[:6]}")
    session.add(project)
    session.commit()
    return project


# 1. Normal natural-language DPR
def test_normal_natural_language_dpr(session) -> None:
    project = create_test_project(session)
    dpr_text = (
        "Piping crew completed erection of the 24-inch line in Unit 3 at approximately 4:30 PM. "
        "Hydrotest preparation has started."
    )
    service = IngestionService(session)
    source, evidence = service.import_text_evidence(
        project_id=project.project_id,
        raw_text=dpr_text,
        source_name="daily_site_report.txt",
        source_type=SourceType.DAILY_REPORT,
    )

    assert source.status == ImportStatus.COMPLETED
    assert evidence is not None
    assert evidence.raw_text == dpr_text

    # Extract using offline deterministic mock provider
    provider = DeterministicMockProvider()
    extractor = ExtractionService(session, provider=provider)
    interpretations = extractor.extract_evidence(evidence.evidence_id)

    assert len(interpretations) == 2
    piping = next(item for item in interpretations if "erection" in item.activity_description.lower())
    hydro = next(item for item in interpretations if "hydrotest" in item.activity_description.lower())

    assert piping.discipline == "Piping"
    assert piping.location == "Unit 3"
    assert piping.status == ActivityStatus.COMPLETED
    assert piping.progress == 100.0

    assert hydro.discipline == "Piping"
    assert hydro.status == ActivityStatus.IN_PROGRESS


# 2. Empty report
def test_empty_report_raises_error(session, tmp_path) -> None:
    project = create_test_project(session)
    service = IngestionService(session)

    # Empty text string recorded as failed source
    source, evidence = service.import_text_evidence(
        project_id=project.project_id,
        raw_text="   \n  \t  ",
        source_name="empty.txt",
        source_type=SourceType.DAILY_REPORT,
    )
    assert source.status == ImportStatus.FAILED
    assert "empty" in (source.error_message or "").lower()
    assert evidence is None

    # Empty file recorded as failed source
    empty_file = tmp_path / "empty_report.txt"
    empty_file.write_text("   ", encoding="utf-8")
    source = service.import_evidence(
        project_id=project.project_id,
        source_path=empty_file,
        source_name="empty_report.txt",
        source_type=SourceType.DAILY_REPORT,
    )
    assert source.status == ImportStatus.FAILED
    assert "empty" in (source.error_message or "").lower()



# 3. Missing timestamp does not hallucinate dates
def test_missing_timestamp_preserves_null(session) -> None:
    project = create_test_project(session)
    raw_text = "Piping crew erected 24-inch line in Unit 3 at approximately 4:30 PM without specifying date."
    service = IngestionService(session)
    source, evidence = service.import_text_evidence(
        project_id=project.project_id,
        raw_text=raw_text,
        source_name="dpr_no_date.txt",
        source_type=SourceType.DAILY_REPORT,
    )

    provider = DeterministicMockProvider()
    extractor = ExtractionService(session, provider=provider)
    interpretations = extractor.extract_evidence(evidence.evidence_id)

    assert len(interpretations) >= 1
    # Check that actual_end is not hallucinated when text only has time
    obs = interpretations[0]
    assert obs.actual_end is None


# 4. Multiple observations in one report
def test_multiple_observations_in_one_report(session) -> None:
    project = create_test_project(session)
    multi_text = (
        "Civil crew finished excavation in Unit 1. "
        "Electrical team installed cable tray in Unit 2 at 75% progress."
    )
    service = IngestionService(session)
    source, evidence = service.import_text_evidence(
        project_id=project.project_id,
        raw_text=multi_text,
        source_name="multi_report.txt",
        source_type=SourceType.DAILY_REPORT,
    )

    provider = DeterministicMockProvider()
    extractor = ExtractionService(session, provider=provider)
    interpretations = extractor.extract_evidence(evidence.evidence_id)

    assert len(interpretations) == 2
    disciplines = {item.discipline for item in interpretations}
    assert "Civil" in disciplines
    assert "Electrical" in disciplines


# 5. TXT ingestion
def test_txt_file_ingestion(session, tmp_path) -> None:
    project = create_test_project(session)
    txt_file = tmp_path / "supervisor_field_log.txt"
    txt_file.write_text("Concrete foundation pour completed in Unit 1 today.", encoding="utf-8")

    service = IngestionService(session)
    source = service.import_evidence(
        project_id=project.project_id,
        source_path=txt_file,
        source_name="supervisor_field_log.txt",
        source_type=SourceType.DAILY_REPORT,
    )

    assert source.status == ImportStatus.COMPLETED
    evidence = list(session.scalars(select(Evidence).where(Evidence.source_name == "supervisor_field_log.txt")))
    assert len(evidence) == 1
    assert "Concrete foundation pour" in evidence[0].raw_text


# 6. PDF text ingestion
def test_pdf_text_ingestion(session, tmp_path) -> None:
    project = create_test_project(session)
    pdf_file = tmp_path / "resident_engineer_report.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 dummy pdf content")

    with patch("app.modules.ingestion.readers.PdfReader") as mock_pdf_reader:
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Piping crew completed erection of the 24-inch line in Unit 3."
        mock_pdf_reader.return_value.pages = [mock_page]

        service = IngestionService(session)
        source = service.import_evidence(
            project_id=project.project_id,
            source_path=pdf_file,
            source_name="resident_engineer_report.pdf",
            source_type=SourceType.SITE_DIARY,
        )

    assert source.status == ImportStatus.COMPLETED
    evidence = list(session.scalars(select(Evidence).where(Evidence.source_name == "resident_engineer_report.pdf")))
    assert len(evidence) == 1
    assert "24-inch line" in evidence[0].raw_text


# 7. XLSX ingestion (flexible columns)
def test_xlsx_ingestion_with_flexible_headers(session, tmp_path) -> None:
    project = create_test_project(session)
    xlsx_file = tmp_path / "discipline_progress.xlsx"

    wb = Workbook()
    ws = wb.active
    ws.append(["Date", "Trade", "Unit", "Task", "Status", "Progress_Percent"])
    ws.append(["2026-09-08", "Piping", "Unit 3", "Erect Line 24-XX", "Completed", "100%"])
    ws.append(["2026-09-08", "Electrical", "Substation", "Install Transformer Foundation", "In Progress", "45%"])
    wb.save(xlsx_file)

    service = IngestionService(session)
    source = service.import_evidence(
        project_id=project.project_id,
        source_path=xlsx_file,
        source_name="discipline_progress.xlsx",
        source_type=SourceType.DISCIPLINE_SPREADSHEET,
    )

    assert source.status == ImportStatus.COMPLETED
    assert source.records_imported == 2
    evidence = list(session.scalars(select(Evidence).where(Evidence.source_name == "discipline_progress.xlsx")))
    assert len(evidence) == 2
    assert any(e.extracted_activity_description == "Erect Line 24-XX" for e in evidence)


# 8. CSV ingestion (flexible columns)
def test_csv_ingestion_with_flexible_headers(session, tmp_path) -> None:
    project = create_test_project(session)
    csv_file = tmp_path / "contractor_progress.csv"
    csv_file.write_text(
        "Report_Date,Contractor_Name,Work_Performed,State,%\n"
        "2026-09-08,Apex Piping,Line 24 installation,in_progress,80%\n",
        encoding="utf-8",
    )

    service = IngestionService(session)
    source = service.import_evidence(
        project_id=project.project_id,
        source_path=csv_file,
        source_name="contractor_progress.csv",
        source_type=SourceType.CONTRACTOR_SPREADSHEET,
    )

    assert source.status == ImportStatus.COMPLETED
    assert source.records_imported == 1
    evidence = list(session.scalars(select(Evidence).where(Evidence.source_name == "contractor_progress.csv")))
    assert len(evidence) == 1
    assert evidence[0].extracted_activity_description == "Line 24 installation"
    assert evidence[0].extracted_progress == 80.0


# 9. Malformed file error handling
def test_malformed_pdf_and_file_handling(session, tmp_path) -> None:
    project = create_test_project(session)
    service = IngestionService(session)

    # Malformed text file disguised as pdf
    bad_pdf = tmp_path / "corrupt.pdf"
    bad_pdf.write_bytes(b"%PDF-1.4 CORRUPT NOT VALID")

    source = service.import_evidence(
        project_id=project.project_id,
        source_path=bad_pdf,
        source_name="corrupt.pdf",
        source_type=SourceType.DAILY_REPORT,
    )
    assert source.status == ImportStatus.FAILED
    assert source.error_message is not None


# 10. Invalid extracted schema handling
def test_invalid_extracted_schema_rejected(session) -> None:
    project = create_test_project(session)
    evidence = Evidence(
        project_id=project.project_id,
        source_type=SourceType.DAILY_REPORT,
        source_name="site_note.txt",
        source_timestamp=datetime(2026, 9, 10, tzinfo=UTC),
        raw_text="Random note",
    )
    session.add(evidence)
    session.commit()

    # Invalid JSON missing required fields
    invalid_json = json.dumps({"observations": [{"activity_description": "x"}]})
    mock_provider = MagicMock()
    mock_provider.extract_progress.return_value = invalid_json
    mock_provider.provider_name = "mock"
    mock_provider.model_name = "mock"

    service = ExtractionService(session, provider=mock_provider, max_attempts=1)
    with pytest.raises(Exception):
        service.extract_evidence(evidence.evidence_id)


# 11. Existing OBSERVATION| format backwards compatibility
def test_existing_observation_format_backwards_compatible(session, tmp_path) -> None:
    project = create_test_project(session)
    pipe_file = tmp_path / "supervisor_pipe.txt"
    pipe_file.write_text(
        "OBSERVATION|2026-09-06T08:00:00Z|Piping|Unit 3|completed|100|24 inch line erection completed in Unit 3.|0.98\n",
        encoding="utf-8",
    )

    service = IngestionService(session)
    source = service.import_evidence(
        project_id=project.project_id,
        source_path=pipe_file,
        source_name="supervisor_pipe.txt",
        source_type=SourceType.DAILY_REPORT,
    )

    assert source.status == ImportStatus.COMPLETED
    assert source.records_imported == 1
    evidence = list(session.scalars(select(Evidence).where(Evidence.source_name == "supervisor_pipe.txt")))
    assert len(evidence) == 1
    assert evidence[0].extracted_progress == 100.0
    assert evidence[0].discipline == "Piping"


# 12. End-to-end integration into matching -> reconciliation -> safety gate
def test_extracted_event_flows_to_matching_and_reconciliation(session) -> None:
    project = create_test_project(session)

    # Add schedule activity
    activity = Activity(
        project_id=project.project_id,
        external_activity_id="PIP001",
        discipline="Piping",
        description="Erect Line 24-XX",
        location="Unit 3",
        planned_start=datetime(2026, 9, 1, tzinfo=UTC).date(),
        planned_finish=datetime(2026, 9, 10, tzinfo=UTC).date(),
        level=5,
        status=ActivityStatus.NOT_STARTED,
    )
    session.add(activity)
    session.commit()

    # Ingest natural language DPR
    dpr_text = "Piping crew completed erection of the 24-inch line in Unit 3 at approximately 4:30 PM."
    service = IngestionService(session)
    source, evidence = service.import_text_evidence(
        project_id=project.project_id,
        raw_text=dpr_text,
        source_name="field_dpr.txt",
        source_type=SourceType.DAILY_REPORT,
    )

    # Extract
    provider = DeterministicMockProvider()
    extractor = ExtractionService(session, provider=provider)
    interpretations = extractor.extract_evidence(evidence.evidence_id)
    assert len(interpretations) >= 1
    interp = interpretations[0]

    # Normalize
    normalizer = NormalizationService(session, provider=provider)
    normalizer.normalize_observation(interp.observation_id)

    # Match
    matcher = MatchingService(session, embedding_provider=DeterministicEmbeddingProvider())
    match_response = matcher.match_observation(interp.observation_id)
    assert match_response.outcome.value in {"matched", "ambiguous", "needs_review"}
    assert len(match_response.candidates) > 0
    assert match_response.candidates[0].external_activity_id == "PIP001"

    # Reconcile
    reconciler = ReconciliationService(session)
    rec_response = reconciler.reconcile_activity(activity.activity_id)

    assert rec_response.activity_id == activity.activity_id
    assert rec_response.confidence > 0
    assert rec_response.reconciled_status in {"completed", "in_progress"}

    # Verify safety gate behavior: Reconciliation record exists and schedule is safely updated or flagged
    reconciliation = session.scalar(select(Reconciliation).where(Reconciliation.activity_id == activity.activity_id))
    assert reconciliation is not None
