import uuid

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.database.models import Activity, Evidence, ImportedSource, Project, Schedule


class ProjectRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, project: Project) -> Project:
        self.session.add(project)
        return project

    def get(self, project_id: uuid.UUID) -> Project | None:
        return self.session.get(Project, project_id)


class ScheduleRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, schedule: Schedule) -> Schedule:
        self.session.add(schedule)
        return schedule


class ActivityRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, activity: Activity) -> Activity:
        self.session.add(activity)
        return activity

    def for_project(self, project_id: uuid.UUID) -> list[Activity]:
        statement: Select[tuple[Activity]] = (
            select(Activity)
            .where(Activity.project_id == project_id)
            .order_by(Activity.external_activity_id)
        )
        return list(self.session.scalars(statement))


class EvidenceRepository:
    """Append-only evidence access. Corrections are represented by new evidence rows."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, evidence: Evidence) -> Evidence:
        self.session.add(evidence)
        return evidence

    def for_project(self, project_id: uuid.UUID) -> list[Evidence]:
        statement: Select[tuple[Evidence]] = (
            select(Evidence)
            .where(Evidence.project_id == project_id)
            .order_by(Evidence.source_timestamp.desc())
        )
        return list(self.session.scalars(statement))


class ImportedSourceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, import_id: uuid.UUID) -> ImportedSource | None:
        return self.session.get(ImportedSource, import_id)

    def for_project(self, project_id: uuid.UUID) -> list[ImportedSource]:
        statement: Select[tuple[ImportedSource]] = (
            select(ImportedSource)
            .where(ImportedSource.project_id == project_id)
            .order_by(ImportedSource.created_at.desc())
        )
        return list(self.session.scalars(statement))
