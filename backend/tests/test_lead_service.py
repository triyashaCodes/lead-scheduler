import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.data_acceses.email_event_data_access import EmailEventDataAccess
from app.data_acceses.lead_data_access import LeadDataAccess
from app.models import Base, EmailEvent, EmailKind, EmailStatus, LeadState
from app.schemas.lead import LeadCreate
from app.services.lead_exceptions import (
    InvalidStateTransitionError,
    LeadNotFoundError,
)
from app.services.lead_service import LeadService
from app.storage.local_resume_storage import LocalResumeStorage
from app.storage.resume_storage import (
    EmptyResumeError,
    ResumeNotFoundError,
    ResumeTooLargeError,
    UnsupportedResumeTypeError,
)

MAX_BYTES = 1024
PDF = b"%PDF-1.7\n%%EOF\n"
KEY_PATTERN = re.compile(r"^[0-9a-f-]{36}\.pdf$")
ATTORNEYS = ["one@firm.example", "two@firm.example"]


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def data_access(session: Session) -> LeadDataAccess:
    return LeadDataAccess(session)


@pytest.fixture
def email_events(session: Session) -> EmailEventDataAccess:
    return EmailEventDataAccess(session)


@pytest.fixture
def storage(tmp_path: Path) -> LocalResumeStorage:
    return LocalResumeStorage(tmp_path / "resumes", max_bytes=MAX_BYTES)


@pytest.fixture
def service(
    data_access: LeadDataAccess,
    storage: LocalResumeStorage,
    email_events: EmailEventDataAccess,
) -> LeadService:
    return LeadService(data_access, storage, email_events, ATTORNEYS)


def lead_data(email: str = "ada@example.com") -> LeadCreate:
    return LeadCreate(first_name="Ada", last_name="Lovelace", email=email)


def stored_files(storage: LocalResumeStorage) -> list[Path]:
    return list(storage._directory.iterdir())


# create_lead


def test_create_lead_persists_a_pending_lead_and_stores_the_resume(
    service: LeadService, data_access: LeadDataAccess, storage: LocalResumeStorage
) -> None:
    lead = service.create_lead(lead_data(), PDF, "cv.pdf")

    assert lead.state == LeadState.PENDING
    assert lead.reached_out_at is None
    assert lead.reached_out_by is None
    assert KEY_PATTERN.match(lead.resume_path)
    assert [f.name for f in stored_files(storage)] == [lead.resume_path]
    assert data_access.get_by_id(lead.id) is not None


def test_create_lead_records_one_pending_email_per_recipient(
    service: LeadService, email_events: EmailEventDataAccess
) -> None:
    lead = service.create_lead(lead_data(), PDF, "cv.pdf")

    events = email_events.list_by_lead(lead.id)
    assert {e.status for e in events} == {EmailStatus.PENDING}
    assert sorted((e.kind.value, e.recipient) for e in events) == sorted(
        [
            (EmailKind.PROSPECT_CONFIRMATION.value, "ada@example.com"),
            *[(EmailKind.ATTORNEY_NOTIFICATION.value, a) for a in ATTORNEYS],
        ]
    )


def test_create_lead_never_uses_the_client_filename(
    service: LeadService, storage: LocalResumeStorage, tmp_path: Path
) -> None:
    lead = service.create_lead(lead_data(), PDF, "../../evil.pdf")

    assert KEY_PATTERN.match(lead.resume_path)
    assert [f.name for f in stored_files(storage)] == [lead.resume_path]
    assert not (tmp_path / "evil.pdf").exists()


@pytest.mark.parametrize(
    ("content", "error"),
    [
        (b"", EmptyResumeError),
        (PDF.ljust(MAX_BYTES + 1, b"0"), ResumeTooLargeError),
        (b"not a resume", UnsupportedResumeTypeError),
    ],
    ids=["empty", "oversize", "wrong-type"],
)
def test_create_lead_with_an_invalid_resume_creates_nothing(
    service: LeadService,
    data_access: LeadDataAccess,
    email_events: EmailEventDataAccess,
    storage: LocalResumeStorage,
    content: bytes,
    error: type[Exception],
) -> None:
    with pytest.raises(error):
        service.create_lead(lead_data(), content, "cv.pdf")

    assert data_access.count() == 0
    assert email_events.list_pending_by_lead("any") == []
    assert stored_files(storage) == []


def test_create_lead_removes_the_stored_resume_if_saving_the_lead_fails(
    service: LeadService,
    session: Session,
    data_access: LeadDataAccess,
    storage: LocalResumeStorage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail() -> None:
        raise RuntimeError("database down")

    monkeypatch.setattr(data_access, "commit", fail)

    with pytest.raises(RuntimeError):
        service.create_lead(lead_data(), PDF, "cv.pdf")

    assert stored_files(storage) == []
    session.rollback()
    assert data_access.count() == 0
    assert session.query(EmailEvent).count() == 0


# get_lead / list_leads


def test_get_lead_returns_the_lead(service: LeadService) -> None:
    lead = service.create_lead(lead_data(), PDF, "cv.pdf")
    assert service.get_lead(lead.id).id == lead.id


def test_get_lead_unknown_id_raises(service: LeadService) -> None:
    with pytest.raises(LeadNotFoundError):
        service.get_lead("missing")


def test_list_leads_filters_by_state_and_returns_the_total(
    service: LeadService,
) -> None:
    first = service.create_lead(lead_data("a@example.com"), PDF, "cv.pdf")
    service.create_lead(lead_data("b@example.com"), PDF, "cv.pdf")
    service.mark_reached_out(first.id, "attorney@example.com")

    everything, total = service.list_leads()
    pending, pending_total = service.list_leads(state=LeadState.PENDING)
    reached, reached_total = service.list_leads(state=LeadState.REACHED_OUT)

    assert (len(everything), total) == (2, 2)
    assert [lead.email for lead in pending] == ["b@example.com"]
    assert pending_total == 1
    assert [lead.id for lead in reached] == [first.id]
    assert reached_total == 1


# mark_reached_out


def test_mark_reached_out_records_state_time_and_attorney(
    service: LeadService, data_access: LeadDataAccess
) -> None:
    lead = service.create_lead(lead_data(), PDF, "cv.pdf")

    updated = service.mark_reached_out(lead.id, "attorney@example.com")

    assert updated.state == LeadState.REACHED_OUT
    assert updated.reached_out_at is not None
    assert updated.reached_out_by == "attorney@example.com"
    persisted = data_access.get_by_id(lead.id)
    assert persisted is not None
    assert persisted.state == LeadState.REACHED_OUT


def test_mark_reached_out_unknown_lead_raises(service: LeadService) -> None:
    with pytest.raises(LeadNotFoundError):
        service.mark_reached_out("missing", "attorney@example.com")


def test_mark_reached_out_twice_raises_and_keeps_the_first_attorney(
    service: LeadService,
) -> None:
    lead = service.create_lead(lead_data(), PDF, "cv.pdf")
    service.mark_reached_out(lead.id, "first@example.com")
    first_time = service.get_lead(lead.id).reached_out_at

    with pytest.raises(InvalidStateTransitionError) as excinfo:
        service.mark_reached_out(lead.id, "second@example.com")

    assert excinfo.value.current == LeadState.REACHED_OUT
    assert excinfo.value.target == LeadState.REACHED_OUT
    unchanged = service.get_lead(lead.id)
    assert unchanged.reached_out_by == "first@example.com"
    assert unchanged.reached_out_at == first_time


# resume filename and open_resume


def test_create_lead_keeps_the_original_filename_as_text_only(
    service: LeadService, storage: LocalResumeStorage
) -> None:
    lead = service.create_lead(lead_data(), PDF, "  My CV.pdf ")

    assert lead.resume_filename == "My CV.pdf"
    assert KEY_PATTERN.match(lead.resume_path)
    assert [f.name for f in stored_files(storage)] == [lead.resume_path]


def test_open_resume_returns_the_stored_file_and_its_type(service: LeadService) -> None:
    lead = service.create_lead(lead_data(), PDF, "cv.pdf")

    resume = service.open_resume(lead.id)

    with resume.stream:
        assert resume.stream.read() == PDF
    assert resume.content_type == "application/pdf"
    assert resume.extension == ".pdf"
    assert resume.original_filename == "cv.pdf"


def test_open_resume_unknown_lead_raises(service: LeadService) -> None:
    with pytest.raises(LeadNotFoundError):
        service.open_resume("missing")


def test_open_resume_raises_when_the_file_is_gone(
    service: LeadService, storage: LocalResumeStorage
) -> None:
    lead = service.create_lead(lead_data(), PDF, "cv.pdf")
    for path in stored_files(storage):
        path.unlink()

    with pytest.raises(ResumeNotFoundError):
        service.open_resume(lead.id)
