"""Development-only sample data for exercising the future planner workflow."""

from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import (
    Activity,
    ActivityStatus,
    ConflictSeverity,
    ConflictType,
    Evidence,
    EvidenceConflict,
    Project,
    ResolutionStatus,
    Schedule,
    SourceType,
)


DEMO_PROJECT_NAME = "Metro Station Package A"


def seed_demo_data(session: Session) -> Project:
    """Insert a stable, idempotent MVP data set. It does not reconcile evidence."""
    existing = session.scalar(select(Project).where(Project.name == DEMO_PROJECT_NAME))
    if existing is not None:
        return existing

    project = Project(
        name=DEMO_PROJECT_NAME,
        description="Sample L5/L6 schedule and field observations for MVP development.",
    )
    schedule = Schedule(
        project=project,
        source_file="sample/metro_station_l6_v1.xlsx",
        version="v1",
        imported_at=datetime(2026, 9, 1, 9, 0, tzinfo=UTC),
    )
    foundations = Activity(
        project=project,
        external_activity_id="L5-FOUND",
        discipline="Civil",
        description="Station foundations",
        location="Station A",
        planned_start=date(2026, 9, 1),
        planned_finish=date(2026, 9, 30),
        level=5,
        status=ActivityStatus.IN_PROGRESS,
    )
    excavation = Activity(
        project=project,
        external_activity_id="L6-EXC-001",
        discipline="Civil",
        description="Excavation for east foundation block",
        location="Station A east block",
        planned_start=date(2026, 9, 1),
        planned_finish=date(2026, 9, 8),
        parent_activity=foundations,
        level=6,
        status=ActivityStatus.NOT_STARTED,
    )
    reinforcement = Activity(
        project=project,
        external_activity_id="L6-REBAR-002",
        discipline="Civil",
        description="Reinforcement installation for east foundation block",
        location="Station A east block",
        planned_start=date(2026, 9, 9),
        planned_finish=date(2026, 9, 16),
        parent_activity=foundations,
        level=6,
        status=ActivityStatus.NOT_STARTED,
    )
    concreting = Activity(
        project=project,
        external_activity_id="L6-CONC-003",
        discipline="Civil",
        description="Concrete pour for east foundation block",
        location="Station A east block",
        planned_start=date(2026, 9, 17),
        planned_finish=date(2026, 9, 23),
        parent_activity=foundations,
        level=6,
        status=ActivityStatus.NOT_STARTED,
    )

    progress_report_time = datetime(2026, 9, 12, 18, 0, tzinfo=UTC)
    spreadsheet_time = datetime(2026, 9, 13, 10, 0, tzinfo=UTC)
    rebar_dpr = Evidence(
        project=project,
        source_type=SourceType.DAILY_REPORT,
        source_name="DPR-2026-09-12.pdf",
        source_timestamp=progress_report_time,
        raw_text="East foundation excavation is complete. Rebar fixing has commenced.",
        raw_reference="sample/DPR-2026-09-12.pdf#page=2",
        extracted_activity_description="Rebar fixing east foundation block",
        extracted_status=ActivityStatus.IN_PROGRESS,
        extracted_progress=20.0,
        discipline="Civil",
        location="Station A east block",
        extraction_confidence=0.89,
    )
    rebar_spreadsheet = Evidence(
        project=project,
        source_type=SourceType.CONTRACTOR_SPREADSHEET,
        source_name="Civil-progress-2026-09-12.xlsx",
        source_timestamp=spreadsheet_time,
        raw_text="L6-REBAR-002 | Reinforcement installation | 100% | Completed",
        raw_reference="sample/Civil-progress-2026-09-12.xlsx#Rebar!A14:D14",
        extracted_activity_description="Reinforcement installation for east foundation block",
        extracted_status=ActivityStatus.COMPLETED,
        extracted_progress=100.0,
        discipline="Civil",
        location="Station A east block",
        extraction_confidence=0.97,
    )
    excavation_dpr = Evidence(
        project=project,
        source_type=SourceType.DAILY_REPORT,
        source_name="DPR-2026-09-13.pdf",
        source_timestamp=datetime(2026, 9, 13, 18, 0, tzinfo=UTC),
        raw_text="Excavation for the east foundation block is complete and awaiting inspection.",
        raw_reference="sample/DPR-2026-09-13.pdf#page=2",
        extracted_activity_description="East foundation excavation",
        extracted_status=ActivityStatus.COMPLETED,
        extracted_progress=100.0,
        discipline="Civil",
        location="Station A east block",
        extraction_confidence=0.92,
    )
    concrete_plan = Evidence(
        project=project,
        source_type=SourceType.DISCIPLINE_SPREADSHEET,
        source_name="Concrete-plan-2026-09-13.xlsx",
        source_timestamp=spreadsheet_time,
        raw_text="East block concrete pour has not started.",
        raw_reference="sample/Concrete-plan-2026-09-13.xlsx#Plan!B8",
        extracted_activity_description="Concrete pour for east foundation block",
        extracted_status=ActivityStatus.NOT_STARTED,
        extracted_progress=0.0,
        discipline="Civil",
        location="Station A east block",
        extraction_confidence=0.95,
    )
    session.add_all(
        [
            schedule,
            foundations,
            excavation,
            reinforcement,
            concreting,
            rebar_dpr,
            rebar_spreadsheet,
            excavation_dpr,
            concrete_plan,
        ]
    )
    session.flush()
    session.add(
        EvidenceConflict(
            activity=reinforcement,
            conflict_type=ConflictType.STATUS,
            description=(
                "The daily report says rebar fixing is in progress at 20%, while the "
                "contractor spreadsheet reports the same east-block activity as complete."
            ),
            severity=ConflictSeverity.HIGH,
            resolution_status=ResolutionStatus.OPEN,
        )
    )
    session.commit()
    return project
