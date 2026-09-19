import logging
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.data_acceses.email_event_data_access import EmailEventDataAccess
from app.models import Base, EmailEvent, EmailKind, EmailStatus, Lead
from app.services.email_service import (
    ConsoleEmailService,
    EmailMessage,
    EmailSendError,
    EmailService,
    SmtpEmailService,
    build_email_service,
)
from app.services.lead_email_service import LeadEmailService
from tests.fakes import FakeEmailService

ATTORNEYS = ["one@firm.example", "two@firm.example"]
FRONTEND = "http://localhost:3000/"


@pytest.fixture
def session_factory(tmp_path: Path) -> sessionmaker[Session]:
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(engine)


def make_lead(
    session_factory: sessionmaker[Session],
    first_name: str = "Ada",
    last_name: str = "Lovelace",
    with_events: bool = True,
) -> str:
    """Create a lead and, like LeadService, its PENDING email rows."""
    with session_factory() as session:
        lead = Lead(
            first_name=first_name,
            last_name=last_name,
            email="ada@example.com",
            resume_path="secret-key.pdf",
        )
        session.add(lead)
        session.flush()
        if with_events:
            recipients = [(EmailKind.PROSPECT_CONFIRMATION, "ada@example.com")]
            recipients += [(EmailKind.ATTORNEY_NOTIFICATION, a) for a in ATTORNEYS]
            for kind, recipient in recipients:
                session.add(EmailEvent(lead_id=lead.id, kind=kind, recipient=recipient))
        session.commit()
        return lead.id


def make_service(
    session_factory: sessionmaker[Session], email_service: EmailService
) -> LeadEmailService:
    return LeadEmailService(
        session_factory=session_factory,
        email_service=email_service,
        sender="no-reply@firm.example",
        frontend_url=FRONTEND,
    )


def load_events(session_factory: sessionmaker[Session], lead_id: str):
    with session_factory() as session:
        return EmailEventDataAccess(session).list_by_lead(lead_id)


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "database_url": "sqlite://",
        "frontend_origin": "http://localhost:3000",
        "resume_storage_dir": "./r",
        "resume_max_bytes": 1024,
        "google_client_id": "x",
        "attorney_emails": "a@firm.example, b@firm.example",
        "email_from": "no-reply@firm.example",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


# Happy path


def test_sends_confirmation_and_attorney_notifications_and_records_sent(
    session_factory: sessionmaker[Session],
) -> None:
    lead_id = make_lead(session_factory)
    fake = FakeEmailService()

    make_service(session_factory, fake).send_lead_emails(lead_id)

    assert sorted(m.to for m in fake.sent) == sorted(["ada@example.com", *ATTORNEYS])
    events = load_events(session_factory, lead_id)
    assert len(events) == 3
    assert {e.status for e in events} == {EmailStatus.SENT}
    assert all(e.attempts == 1 and e.sent_at is not None for e in events)
    assert [e.kind for e in events].count(EmailKind.ATTORNEY_NOTIFICATION) == 2
    assert {e.recipient for e in events} == {"ada@example.com", *ATTORNEYS}

    notification = next(m for m in fake.sent if m.to == ATTORNEYS[0])
    assert f"http://localhost:3000/leads/{lead_id}" in notification.body
    assert "secret-key.pdf" not in notification.body


# Failures and edge cases


def test_attorney_email_links_to_the_frontend_lead_page(
    session_factory: sessionmaker[Session],
) -> None:
    lead_id = make_lead(session_factory)
    fake = FakeEmailService()

    # FRONTEND ends with a slash, as an origin might be configured.
    make_service(session_factory, fake).send_lead_emails(lead_id)

    body = next(m.body for m in fake.sent if m.to == ATTORNEYS[0])
    links = [word for word in body.split() if word.startswith("http")]
    assert links == [f"http://localhost:3000/leads/{lead_id}"]
    assert "/internal/" not in body
    # The prospect's confirmation carries no link at all.
    prospect = next(m.body for m in fake.sent if m.to == "ada@example.com")
    assert "http" not in prospect


def test_a_failed_send_is_recorded_and_logged_not_raised(
    session_factory: sessionmaker[Session], caplog: pytest.LogCaptureFixture
) -> None:
    lead_id = make_lead(session_factory)
    fake = FakeEmailService(fail_for={"ada@example.com"})

    with caplog.at_level(logging.ERROR):
        make_service(session_factory, fake).send_lead_emails(lead_id)

    by_recipient = {e.recipient: e for e in load_events(session_factory, lead_id)}
    failed = by_recipient["ada@example.com"]
    assert failed.status == EmailStatus.FAILED
    assert failed.attempts == 1
    assert failed.last_error == "mail server unavailable"
    assert failed.sent_at is None
    assert by_recipient[ATTORNEYS[0]].status == EmailStatus.SENT
    assert by_recipient[ATTORNEYS[1]].status == EmailStatus.SENT
    assert "failed" in caplog.text


def test_unexpected_errors_from_the_sender_are_also_contained(
    session_factory: sessionmaker[Session],
) -> None:
    class Exploding(EmailService):
        def send(self, message: EmailMessage) -> None:
            raise RuntimeError("boom")

    lead_id = make_lead(session_factory)
    make_service(session_factory, Exploding()).send_lead_emails(lead_id)

    events = load_events(session_factory, lead_id)
    assert {e.status for e in events} == {EmailStatus.FAILED}


def test_unknown_lead_sends_nothing_and_does_not_raise(
    session_factory: sessionmaker[Session], caplog: pytest.LogCaptureFixture
) -> None:
    fake = FakeEmailService()

    with caplog.at_level(logging.ERROR):
        make_service(session_factory, fake).send_lead_emails("missing")

    assert fake.sent == []
    assert "not found" in caplog.text


def test_only_pending_emails_are_sent_so_a_second_call_sends_nothing(
    session_factory: sessionmaker[Session],
) -> None:
    lead_id = make_lead(session_factory)
    fake = FakeEmailService()
    service = make_service(session_factory, fake)

    service.send_lead_emails(lead_id)
    service.send_lead_emails(lead_id)

    assert len(fake.sent) == 3
    assert {e.attempts for e in load_events(session_factory, lead_id)} == {1}


def test_failed_emails_are_not_resent_automatically(
    session_factory: sessionmaker[Session],
) -> None:
    lead_id = make_lead(session_factory)
    make_service(
        session_factory, FakeEmailService(fail_for={"ada@example.com"})
    ).send_lead_emails(lead_id)

    fake = FakeEmailService()
    make_service(session_factory, fake).send_lead_emails(lead_id)

    assert fake.sent == []


def test_lead_with_no_email_rows_sends_nothing(
    session_factory: sessionmaker[Session],
) -> None:
    lead_id = make_lead(session_factory, with_events=False)
    fake = FakeEmailService()

    make_service(session_factory, fake).send_lead_emails(lead_id)

    assert fake.sent == []
    assert load_events(session_factory, lead_id) == []


def test_newlines_are_stripped_from_names_in_subjects(
    session_factory: sessionmaker[Session],
) -> None:
    lead_id = make_lead(
        session_factory,
        first_name="Ada\r\nBcc: evil@example.com",
        last_name="Love\nlace",
    )
    fake = FakeEmailService()

    make_service(session_factory, fake).send_lead_emails(lead_id)

    for message in fake.sent:
        assert "\r" not in message.subject and "\n" not in message.subject
    subjects = {m.to: m.subject for m in fake.sent}
    assert subjects["ada@example.com"] == "We received your application, Ada Bcc: evil@example.com"
    assert subjects[ATTORNEYS[0]] == "New lead: Ada Bcc: evil@example.com Love lace"


# SMTP fallback


def test_console_fallback_is_used_when_smtp_is_unset() -> None:
    assert isinstance(build_email_service(make_settings()), ConsoleEmailService)
    assert isinstance(
        build_email_service(make_settings(smtp_host="")), ConsoleEmailService
    )


def test_smtp_service_is_used_when_smtp_host_is_set() -> None:
    service = build_email_service(make_settings(smtp_host="smtp.example.com"))
    assert isinstance(service, SmtpEmailService)


def test_console_service_keeps_personal_data_out_of_the_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    message = EmailMessage("from@x.example", "to@x.example", "Hello", "Body text")

    with caplog.at_level(logging.WARNING):
        ConsoleEmailService().send(message)
    assert "not sent" in caplog.text
    assert "to@x.example" not in caplog.text

    caplog.clear()
    with caplog.at_level(logging.DEBUG):
        ConsoleEmailService().send(message)
    assert "to@x.example" in caplog.text
    assert "Body text" in caplog.text


def test_smtp_connection_failure_becomes_email_send_error() -> None:
    service = SmtpEmailService(host="127.0.0.1", port=1, starttls=False)
    with pytest.raises(EmailSendError):
        service.send(EmailMessage("from@x.example", "to@x.example", "Hi", "Body"))


def test_attorney_email_list_is_parsed_from_the_allowlist() -> None:
    assert make_settings().attorney_email_list == ["a@firm.example", "b@firm.example"]
