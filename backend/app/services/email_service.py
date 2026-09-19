import logging
import smtplib
import ssl
from abc import ABC, abstractmethod
from dataclasses import dataclass
from email.message import EmailMessage as MimeMessage

from app.core.config import Settings

logger = logging.getLogger(__name__)

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


@dataclass(frozen=True)
class EmailMessage:
    """A plain-text email. There is deliberately no attachments field."""

    sender: str
    to: str
    subject: str
    body: str


class EmailSendError(Exception):
    pass


class EmailService(ABC):
    @abstractmethod
    def send(self, message: EmailMessage) -> None:
        """Send the message; raise EmailSendError if it could not be sent."""


class ConsoleEmailService(EmailService):
    """Dev fallback used when SMTP is not configured: logs instead of sending.

    The WARNING line carries no personal data; the full message is logged at
    DEBUG so it only appears when a developer asks for it.
    """

    def send(self, message: EmailMessage) -> None:
        logger.warning("SMTP not configured, email not sent (set log level to DEBUG to see it)")
        logger.debug(
            "Email not sent.\nFrom: %s\nTo: %s\nSubject: %s\n\n%s",
            message.sender,
            message.to,
            message.subject,
            message.body,
        )


class SmtpEmailService(EmailService):
    def __init__(
        self,
        host: str,
        port: int,
        username: str = "",
        password: str = "",
        starttls: bool = True,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._starttls = starttls

    def send(self, message: EmailMessage) -> None:
        # Never send credentials in the clear, except to a local test server.
        if self._username and not self._starttls and self._host not in _LOCAL_HOSTS:
            raise EmailSendError("Refusing to send SMTP credentials without TLS")
        try:
            mime = MimeMessage()
            mime["From"] = message.sender
            mime["To"] = message.to
            mime["Subject"] = message.subject
            mime.set_content(message.body)
            with smtplib.SMTP(self._host, self._port, timeout=10) as smtp:
                if self._starttls:
                    # smtplib's default context does not verify the server's
                    # certificate, so pass one that does.
                    smtp.starttls(context=ssl.create_default_context())
                if self._username:
                    smtp.login(self._username, self._password)
                smtp.send_message(mime)
        except (smtplib.SMTPException, OSError, ValueError) as exc:
            raise EmailSendError(str(exc)) from exc


def build_email_service(settings: Settings) -> EmailService:
    if not settings.smtp_host:
        return ConsoleEmailService()
    return SmtpEmailService(
        host=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_user,
        password=settings.smtp_password.get_secret_value(),
        starttls=settings.smtp_starttls,
    )
