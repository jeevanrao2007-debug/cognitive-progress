from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.routes import imports as imports_route
from app.api.routes.imports import get_session
from app.database.models import Activity, Evidence, ImportStatus, ImportedSource, Project, SourceType
from app.main import app
from app.modules.ingestion.service import IngestionService


SAMPLE_DIR = Path(__file__).parents[2] / "data" / "sample"


def create_project(session):  # type: ignore[no-untyped-def]
    project = Project(name="Unit 3 import test")
    session.add(project)
    session.commit()
    return project


def test_schedule_import_creates_l5_l6_activities(session):  # type: ignore[no-untyped-def]
    project = create_project(session)

    source = IngestionService(session).import_schedule(
        project.project_id,
        SAMPLE_DIR / "oil_india_facility_l5_l6_schedule.csv",
        "oil_india_facility_l5_l6_schedule.csv",
        "v1",
    )

    activities = list(session.scalars(select(Activity).where(Activity.project_id == project.project_id)))
    assert source.status is ImportStatus.COMPLETED
    assert source.records_imported == 12
    assert len(activities) == 12
    assert {activity.level for activity in activities} == {5, 6}
    assert next(item for item in activities if item.external_activity_id == "PIP001").description == "Erect Line 24-XX"


def test_evidence_import_preserves_every_source_observation(session):  # type: ignore[no-untyped-def]
    project = create_project(session)
    service = IngestionService(session)

    daily = service.import_evidence(project.project_id, SAMPLE_DIR / "daily_progress_report_2026-09-24.txt", "daily_progress_report_2026-09-24.txt", SourceType.DAILY_REPORT)
    diary = service.import_evidence(project.project_id, SAMPLE_DIR / "site_diary_2026-09-25.txt", "site_diary_2026-09-25.txt", SourceType.SITE_DIARY)
    contractor = service.import_evidence(project.project_id, SAMPLE_DIR / "contractor_progress_2026-09-25.csv", "contractor_progress_2026-09-25.csv", SourceType.CONTRACTOR_SPREADSHEET)

    evidence = list(session.scalars(select(Evidence).where(Evidence.project_id == project.project_id)))
    assert [daily.records_imported, diary.records_imported, contractor.records_imported] == [8, 8, 8]
    assert len(evidence) == 24
    completed_line_report = next(item for item in evidence if "24 inch line erection completed" in item.raw_text)
    contractor_line_report = next(item for item in evidence if "Line 24 installation equals 80 percent" in item.raw_text)
    assert completed_line_report.extracted_progress == 100
    assert contractor_line_report.extracted_progress == 80
    assert completed_line_report.raw_reference is not None


def test_failed_import_is_recorded_with_validation_errors(session, tmp_path):  # type: ignore[no-untyped-def]
    project = create_project(session)
    invalid_source = tmp_path / "invalid_schedule.csv"
    invalid_source.write_text("external_activity_id,description\nPIP999,Missing required columns\n", encoding="utf-8")

    source = IngestionService(session).import_schedule(project.project_id, invalid_source, "invalid_schedule.csv", "bad-v1")

    persisted = session.get(ImportedSource, source.import_id)
    assert persisted is not None
    assert persisted.status is ImportStatus.FAILED
    assert persisted.records_imported == 0
    assert persisted.validation_errors is not None


def test_schedule_import_endpoint_and_source_list(session, tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    project = create_project(session)
    app.dependency_overrides[get_session] = lambda: session
    monkeypatch.setattr(
        imports_route,
        "get_settings",
        lambda: SimpleNamespace(ingestion_storage_path=str(tmp_path / "imports")),
    )
    try:
        with TestClient(app) as client:
            with (SAMPLE_DIR / "oil_india_facility_l5_l6_schedule.csv").open("rb") as source_file:
                response = client.post(
                    f"/api/v1/projects/{project.project_id}/imports/schedule",
                    data={"version": "api-v1"},
                    files={"file": ("schedule.csv", source_file, "text/csv")},
                )
            assert response.status_code == 200
            assert response.json()["status"] == "completed"
            assert response.json()["records_imported"] == 12

            listed = client.get(f"/api/v1/projects/{project.project_id}/imports")
            assert listed.status_code == 200
            assert len(listed.json()) == 1
    finally:
        app.dependency_overrides.clear()
