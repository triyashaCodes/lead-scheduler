from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import EmailEvent, EmailStatus


class EmailEventDataAccess:
    def __init__(self, db: Session) -> None:
        self._db = db

    def add(self, event: EmailEvent) -> EmailEvent:
        self._db.add(event)
        self._db.flush()
        return event

    def list_by_lead(self, lead_id: str) -> list[EmailEvent]:
        stmt = (
            select(EmailEvent)
            .where(EmailEvent.lead_id == lead_id)
            .order_by(EmailEvent.created_at, EmailEvent.id)
        )
        return list(self._db.scalars(stmt))

    def list_pending_by_lead(self, lead_id: str) -> list[EmailEvent]:
        stmt = (
            select(EmailEvent)
            .where(
                EmailEvent.lead_id == lead_id,
                EmailEvent.status == EmailStatus.PENDING,
            )
            .order_by(EmailEvent.created_at, EmailEvent.id)
        )
        return list(self._db.scalars(stmt))

    def commit(self) -> None:
        self._db.commit()
