import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class EmailKind(str, enum.Enum):
    PROSPECT_CONFIRMATION = "PROSPECT_CONFIRMATION"
    ATTORNEY_NOTIFICATION = "ATTORNEY_NOTIFICATION"


class EmailStatus(str, enum.Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"


class EmailEvent(Base):
    __tablename__ = "email_events"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"), index=True)
    kind: Mapped[EmailKind] = mapped_column(Enum(EmailKind, native_enum=False, length=30))
    recipient: Mapped[str] = mapped_column(String(320))
    status: Mapped[EmailStatus] = mapped_column(
        Enum(EmailStatus, native_enum=False, length=20),
        default=EmailStatus.PENDING,
        index=True,
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
