from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field

from app.models import LeadState


def _ensure_utc(value: datetime) -> datetime:
    # SQLite drops the timezone, so values come back naive but are always UTC.
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


UtcDatetime = Annotated[datetime, AfterValidator(_ensure_utc)]


class LeadCreate(BaseModel):
    """Text fields of the public submission form; the resume arrives as a file upload."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr


class LeadUpdate(BaseModel):
    """Only the state may be sent; the acting attorney comes from the auth token."""

    model_config = ConfigDict(extra="forbid")

    state: Literal[LeadState.REACHED_OUT]


class LeadRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    first_name: str
    last_name: str
    email: EmailStr
    state: LeadState
    created_at: UtcDatetime
    reached_out_at: UtcDatetime | None
    reached_out_by: str | None


class LeadList(BaseModel):
    items: list[LeadRead]
    total: int
    page: int
    page_size: int


class LeadCreated(BaseModel):
    """Public response to a submission: just the id, no personal data."""

    id: str
