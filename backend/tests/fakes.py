from app.services.email_service import EmailMessage, EmailSendError, EmailService


class FakeEmailService(EmailService):
    def __init__(self, fail_for: set[str] | None = None) -> None:
        self.sent: list[EmailMessage] = []
        self._fail_for = fail_for or set()

    def send(self, message: EmailMessage) -> None:
        if message.to in self._fail_for:
            raise EmailSendError("mail server unavailable")
        self.sent.append(message)
