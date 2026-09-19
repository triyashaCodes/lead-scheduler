from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.data_acceses.lead_data_access import LeadDataAccess
from app.models import Base, Lead, LeadState
from app.schemas.lead import LeadCreate, LeadRead, LeadUpdate


@pytest.fixture
def repo() -> LeadDataAccess:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield LeadDataAccess(session)


def make_lead(email: str = "a@example.com", **kwargs) -> Lead:
    return Lead(
        first_name="Ada",
        last_name="Lovelace",
        email=email,
        resume_path="abc.pdf",
        **kwargs,
    )


def test_add_applies_defaults(repo: LeadDataAccess) -> None:
    lead = repo.add(make_lead())
    repo.commit()

    fetched = repo.get_by_id(lead.id)
    assert fetched is not None
    assert fetched.state == LeadState.PENDING
    assert fetched.created_at is not None
    assert fetched.reached_out_at is None
    assert fetched.reached_out_by is None


def test_get_by_id_missing_returns_none(repo: LeadDataAccess) -> None:
    assert repo.get_by_id("missing") is None


def test_list_is_newest_first_and_filters_by_state(repo: LeadDataAccess) -> None:
    now = datetime.now(timezone.utc)
    repo.add(make_lead("old@example.com", created_at=now - timedelta(days=2)))
    repo.add(make_lead("new@example.com", created_at=now))
    repo.add(
        make_lead(
            "done@example.com",
            state=LeadState.REACHED_OUT,
            created_at=now - timedelta(days=1),
        )
    )
    repo.commit()

    assert [lead.email for lead in repo.list()] == [
        "new@example.com",
        "done@example.com",
        "old@example.com",
    ]
    assert [lead.email for lead in repo.list(state=LeadState.REACHED_OUT)] == [
        "done@example.com"
    ]
    assert repo.count() == 3
    assert repo.count(state=LeadState.PENDING) == 2
    assert len(repo.list(limit=1, offset=1)) == 1


def test_create_schema_rejects_bad_email_and_extra_fields() -> None:
    with pytest.raises(ValidationError):
        LeadCreate(first_name="A", last_name="B", email="not-an-email")
    with pytest.raises(ValidationError):
        LeadCreate(first_name="A", last_name="B", email="a@example.com", user="x")


def test_update_schema_only_accepts_reached_out() -> None:
    assert LeadUpdate(state="REACHED_OUT").state == LeadState.REACHED_OUT
    with pytest.raises(ValidationError):
        LeadUpdate(state="PENDING")
    with pytest.raises(ValidationError):
        LeadUpdate(state="REACHED_OUT", reached_out_by="me@example.com")


def test_read_schema_hides_resume_path(repo: LeadDataAccess) -> None:
    lead = repo.add(make_lead())
    repo.commit()
    assert "resume_path" not in LeadRead.model_validate(lead).model_dump()


def test_pages_never_repeat_or_skip_leads_that_share_a_timestamp(
    repo: LeadDataAccess,
) -> None:
    same_moment = datetime.now(timezone.utc)
    for n in range(7):
        repo.add(make_lead(f"same{n}@example.com", created_at=same_moment))
    repo.commit()

    pages = [repo.list(limit=2, offset=offset) for offset in (0, 2, 4, 6)]
    ids = [lead.id for page in pages for lead in page]

    assert len(ids) == 7
    assert len(set(ids)) == 7
