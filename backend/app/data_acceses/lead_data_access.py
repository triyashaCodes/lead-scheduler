from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models import Lead, LeadState


class LeadDataAccess:
    def __init__(self, db: Session) -> None:
        self._db = db

    def add(self, lead: Lead) -> Lead:
        self._db.add(lead)
        self._db.flush()
        return lead

    def get_by_id(self, lead_id: str) -> Lead | None:
        return self._db.get(Lead, lead_id)

    def list(
        self, state: LeadState | None = None, limit: int = 20, offset: int = 0
    ) -> list[Lead]:
        stmt = select(Lead).order_by(Lead.created_at.desc()).limit(limit).offset(offset)
        if state is not None:
            stmt = stmt.where(Lead.state == state)
        return list(self._db.scalars(stmt))

    def count(self, state: LeadState | None = None) -> int:
        stmt = select(func.count()).select_from(Lead)
        if state is not None:
            stmt = stmt.where(Lead.state == state)
        return self._db.scalar(stmt) or 0

    def update_if_state(self, lead_id: str, expected: LeadState, **values: Any) -> bool:
        """Compare-and-set: apply `values` only if the lead is still in `expected`.

        Returns False when another request changed the state first. The check
        and the write are one statement, so two callers cannot both succeed.
        """
        result = self._db.execute(
            update(Lead).where(Lead.id == lead_id, Lead.state == expected).values(**values),
            execution_options={"synchronize_session": "fetch"},
        )
        return result.rowcount == 1

    def refresh(self, lead: Lead) -> Lead:
        self._db.refresh(lead)
        return lead

    def commit(self) -> None:
        self._db.commit()
