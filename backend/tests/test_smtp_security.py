import smtplib
import ssl

import pytest

from app.services.email_service import EmailMessage, EmailSendError, SmtpEmailService

MESSAGE = EmailMessage("from@x.example", "to@x.example", "Hi", "Body")


class FakeSmtp:
    """Records how the SMTP connection was used instead of opening one."""

    instances: list["FakeSmtp"] = []

    def __init__(self, host: str, port: int, timeout: int | None = None) -> None:
        self.host, self.port = host, port
        self.tls_context: ssl.SSLContext | None = None
        self.logged_in = False
        self.sent = False
        FakeSmtp.instances.append(self)

    def __enter__(self) -> "FakeSmtp":
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def starttls(self, context: ssl.SSLContext | None = None) -> None:
        self.tls_context = context

    def login(self, user: str, password: str) -> None:
        self.logged_in = True

    def send_message(self, message: object) -> None:
        self.sent = True


@pytest.fixture(autouse=True)
def fake_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeSmtp.instances.clear()
    monkeypatch.setattr(smtplib, "SMTP", FakeSmtp)


def test_starttls_verifies_the_server_certificate_and_hostname() -> None:
    SmtpEmailService("smtp.gmail.com", 587, "u", "p", starttls=True).send(MESSAGE)

    context = FakeSmtp.instances[0].tls_context
    assert context is not None
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True


def test_credentials_are_not_sent_without_tls_to_a_remote_host() -> None:
    service = SmtpEmailService("smtp.example.com", 25, "u", "p", starttls=False)

    with pytest.raises(EmailSendError, match="without TLS"):
        service.send(MESSAGE)

    assert FakeSmtp.instances == []  # it never even connected


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1"])
def test_a_local_test_server_may_be_used_without_tls(host: str) -> None:
    SmtpEmailService(host, 1025, "u", "p", starttls=False).send(MESSAGE)

    assert FakeSmtp.instances[0].sent is True
    assert FakeSmtp.instances[0].tls_context is None


def test_a_remote_server_without_credentials_needs_no_tls() -> None:
    SmtpEmailService("relay.example.com", 25, "", "", starttls=False).send(MESSAGE)
    assert FakeSmtp.instances[0].sent is True


# Settings hygiene


def _settings(**overrides):
    from app.core.config import Settings

    values = {
        "database_url": "sqlite://",
        "frontend_origin": "http://localhost:3000",
        "resume_storage_dir": "./r",
        "resume_max_bytes": 1024,
        "google_client_id": "x",
        "attorney_emails": "a@firm.example",
        "email_from": "f@firm.example",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_the_smtp_password_is_not_shown_when_settings_are_printed() -> None:
    settings = _settings(smtp_password="s3cret-app-password")

    assert "s3cret-app-password" not in repr(settings)
    assert "s3cret-app-password" not in str(settings)


def test_the_real_password_still_reaches_the_smtp_service() -> None:
    from app.services.email_service import build_email_service

    service = build_email_service(
        _settings(smtp_host="smtp.gmail.com", smtp_user="u", smtp_password="s3cret-app-password")
    )

    assert service._password == "s3cret-app-password"


@pytest.mark.parametrize("configured", ["http://localhost:3000/", " http://localhost:3000 ", "http://localhost:3000//"])
def test_the_frontend_origin_is_normalised_so_cors_matches(configured: str) -> None:
    assert _settings(frontend_origin=configured).frontend_origin == "http://localhost:3000"
