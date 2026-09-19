import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.data_acceses.email_event_data_access import EmailEventDataAccess
from app.data_acceses.lead_data_access import LeadDataAccess
from app.models import Base, EmailEvent, EmailKind, EmailStatus, Lead, LeadState
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


# mark_reached_out: concurrent attorneys (regression test for a lost update)


def test_two_attorneys_marking_at_once_one_wins_and_one_gets_a_conflict(
    tmp_path: Path,
) -> None:
    import threading

    from sqlalchemy.orm import sessionmaker

    engine = create_engine(
        f"sqlite:///{tmp_path / 'race.db'}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    Base.metadata.create_all(engine)
    make_session = sessionmaker(engine, expire_on_commit=False)
    with make_session() as setup:
        setup_da = LeadDataAccess(setup)
        lead = Lead(first_name="A", last_name="B", email="a@b.co", resume_path="k.pdf")
        setup_da.add(lead)
        setup_da.commit()
        lead_id = lead.id

    barrier = threading.Barrier(2)
    results: dict[str, str] = {}

    def attorney(email: str) -> None:
        with make_session() as session:
            data_access = LeadDataAccess(session)
            real_get = data_access.get_by_id

            def get_then_wait(lead_id: str):
                found = real_get(lead_id)
                barrier.wait()  # both attorneys have now read PENDING
                return found

            data_access.get_by_id = get_then_wait  # type: ignore[method-assign]
            svc = LeadService(data_access, None, EmailEventDataAccess(session), [])  # type: ignore[arg-type]
            try:
                svc.mark_reached_out(lead_id, email)
                results[email] = "ok"
            except InvalidStateTransitionError:
                results[email] = "conflict"

    threads = [threading.Thread(target=attorney, args=(e,)) for e in ("a@firm", "b@firm")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(results.values()) == ["conflict", "ok"]
    winner = next(email for email, outcome in results.items() if outcome == "ok")
    with make_session() as check:
        stored = LeadDataAccess(check).get_by_id(lead_id)
    assert stored.state == LeadState.REACHED_OUT
    assert stored.reached_out_by == winner


def test_update_if_state_only_applies_when_the_state_still_matches(
    data_access: LeadDataAccess, service: LeadService
) -> None:
    lead = service.create_lead(lead_data(), PDF, "cv.pdf")

    assert data_access.update_if_state(lead.id, LeadState.REACHED_OUT, reached_out_by="x") is False
    assert data_access.update_if_state(lead.id, LeadState.PENDING, reached_out_by="x") is True


# Confirmation emails are capped per address (so the form cannot flood an inbox)


def confirmations(email_events: EmailEventDataAccess, lead_id: str) -> list:
    return [
        e for e in email_events.list_by_lead(lead_id)
        if e.kind == EmailKind.PROSPECT_CONFIRMATION
    ]


def test_confirmations_stop_after_the_daily_limit_but_the_lead_is_still_saved(
    service: LeadService, data_access: LeadDataAccess, email_events: EmailEventDataAccess
) -> None:
    leads = [service.create_lead(lead_data("victim@example.com"), PDF, "cv.pdf") for _ in range(5)]

    counts = [len(confirmations(email_events, lead.id)) for lead in leads]

    assert counts == [1, 1, 1, 0, 0]  # the default limit is 3 a day
    assert data_access.count() == 5
    # Attorneys are still notified for every lead.
    for lead in leads:
        notified = [e for e in email_events.list_by_lead(lead.id) if e.kind == EmailKind.ATTORNEY_NOTIFICATION]
        assert len(notified) == len(ATTORNEYS)


def test_changing_the_capitals_does_not_bypass_the_limit(
    service: LeadService, email_events: EmailEventDataAccess
) -> None:
    variants = ["victim@example.com", "Victim@Example.com", "VICTIM@EXAMPLE.COM", "victim@EXAMPLE.com"]
    leads = [service.create_lead(lead_data(v), PDF, "cv.pdf") for v in variants]

    assert [len(confirmations(email_events, lead.id)) for lead in leads] == [1, 1, 1, 0]


def test_the_limit_is_per_address(
    service: LeadService, email_events: EmailEventDataAccess
) -> None:
    for _ in range(3):
        service.create_lead(lead_data("a@example.com"), PDF, "cv.pdf")

    other = service.create_lead(lead_data("b@example.com"), PDF, "cv.pdf")

    assert len(confirmations(email_events, other.id)) == 1


def test_confirmations_older_than_a_day_no_longer_count(
    service: LeadService, session: Session, email_events: EmailEventDataAccess
) -> None:
    from datetime import datetime, timedelta, timezone

    first = service.create_lead(lead_data("a@example.com"), PDF, "cv.pdf")
    for _ in range(2):
        service.create_lead(lead_data("a@example.com"), PDF, "cv.pdf")
    old = datetime.now(timezone.utc) - timedelta(days=2)
    for event in session.query(EmailEvent).filter_by(kind=EmailKind.PROSPECT_CONFIRMATION):
        event.created_at = old
    session.commit()

    again = service.create_lead(lead_data("a@example.com"), PDF, "cv.pdf")

    assert len(confirmations(email_events, again.id)) == 1
    assert first.id != again.id


def test_a_custom_limit_can_be_set(
    data_access: LeadDataAccess, storage: LocalResumeStorage, email_events: EmailEventDataAccess
) -> None:
    strict = LeadService(data_access, storage, email_events, ATTORNEYS, max_confirmations_per_address_per_day=1)

    first = strict.create_lead(lead_data("a@example.com"), PDF, "cv.pdf")
    second = strict.create_lead(lead_data("a@example.com"), PDF, "cv.pdf")

    assert len(confirmations(email_events, first.id)) == 1
    assert len(confirmations(email_events, second.id)) == 0
