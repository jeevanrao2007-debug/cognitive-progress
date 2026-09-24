import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.database.models import AuditAction, AuditEvent


class AuditService:
    """Captures append-only, machine-readable decision traces."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def record_created(self, entity_type: str, entity_id: uuid.UUID, after_value: dict[str, Any],
                       explanation: str, actor: str = "reconciliation-engine") -> AuditEvent:
        event = AuditEvent(entity_type=entity_type, entity_id=entity_id, action=AuditAction.CREATED,
            actor=actor, before_value=None, after_value=after_value, explanation=explanation)
        self.session.add(event)
        return event

    def record(self, entity_type: str, entity_id: uuid.UUID, action: AuditAction,
               before_value: dict[str, Any] | None, after_value: dict[str, Any] | None,
               explanation: str, actor: str) -> AuditEvent:
        event = AuditEvent(entity_type=entity_type, entity_id=entity_id, action=action, actor=actor,
            before_value=before_value, after_value=after_value, explanation=explanation)
        self.session.add(event)
        return event
