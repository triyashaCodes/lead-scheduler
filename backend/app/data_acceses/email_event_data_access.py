from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import EmailEvent, EmailKind, EmailStatus


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

    def count_since(self, recipient: str, kind: EmailKind, since: datetime) -> int:
        """How many emails of this kind were recorded for an address since a time.

        The address is compared ignoring case, so changing the capitals does not
        make it look like a different recipient.
        """
        stmt = (
            select(func.count())
            .select_from(EmailEvent)
            .where(
                func.lower(EmailEvent.recipient) == recipient.lower(),
                EmailEvent.kind == kind,
                EmailEvent.created_at >= since,
            )
        )
        return self._db.scalar(stmt) or 0

    def commit(self) -> None:
        self._db.commit()
