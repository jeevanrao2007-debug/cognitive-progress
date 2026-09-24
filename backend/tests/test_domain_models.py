from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database.models import Activity, ActivityStatus, Evidence, Project, SourceType
from app.database.repositories import ActivityRepository, EvidenceRepository
from app.database.seed import DEMO_PROJECT_NAME, seed_demo_data


def test_activity_requires_an_existing_project(session) -> None:  # type: ignore[no-untyped-def]
    activity = Activity(
        project_id=uuid4(),
        external_activity_id="L6-001",
        description="Test activity",
        level=6,
        status=ActivityStatus.NOT_STARTED,
    )
    session.add(activity)

    with pytest.raises(IntegrityError):
        session.commit()


def test_evidence_preserves_raw_content_requirement(session) -> None:  # type: ignore[no-untyped-def]
    project = Project(name="Test project")
    session.add(project)
    session.flush()
    evidence = Evidence(
        project_id=project.project_id,
        source_type=SourceType.DAILY_REPORT,
        source_name="DPR.pdf",
        source_timestamp=datetime.now(UTC),
    )
    session.add(evidence)

    with pytest.raises(IntegrityError):
        session.commit()


def test_seed_data_contains_expected_conflict_and_evidence(session) -> None:  # type: ignore[no-untyped-def]
    project = seed_demo_data(session)
    activities = ActivityRepository(session).for_project(project.project_id)
    evidence = EvidenceRepository(session).for_project(project.project_id)

    assert project.name == DEMO_PROJECT_NAME
    assert len(activities) == 4
    assert len(evidence) == 4
    reinforcement = next(item for item in activities if item.external_activity_id == "L6-REBAR-002")
    assert reinforcement.status is ActivityStatus.NOT_STARTED
    assert len(reinforcement.conflicts) == 1
    assert reinforcement.conflicts[0].severity.value == "high"


def test_seed_data_is_idempotent(session) -> None:  # type: ignore[no-untyped-def]
    first = seed_demo_data(session)
    second = seed_demo_data(session)

    projects = list(session.scalars(select(Project)))
    assert first.project_id == second.project_id
    assert len(projects) == 1
