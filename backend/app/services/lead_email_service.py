import logging
from collections.abc import Callable

from sqlalchemy.orm import Session

from app.data_acceses.email_event_data_access import EmailEventDataAccess
from app.data_acceses.lead_data_access import LeadDataAccess
from app.models import EmailEvent, EmailKind, EmailStatus, Lead
from app.models.base import utcnow
from app.services.email_service import EmailMessage, EmailService

logger = logging.getLogger(__name__)

_MAX_ERROR_LENGTH = 500


def _single_line(text: str) -> str:
    """Collapse all whitespace, including CR/LF, so text is safe in a header."""
    return " ".join(text.split())


class LeadEmailService:
    """Sends the PENDING emails recorded for a lead and updates each EmailEvent.

    The PENDING rows are written by LeadService in the lead's own transaction.
    This runs after the request has finished, so it opens its own session from
    `session_factory` instead of receiving one.
    """

    def __init__(
        self,
        session_factory: Callable[[], Session],
        email_service: EmailService,
        sender: str,
        frontend_url: str,
    ) -> None:
        self._session_factory = session_factory
        self._email_service = email_service
        self._sender = sender
        self._frontend_url = frontend_url.rstrip("/")

    def send_lead_emails(self, lead_id: str) -> None:
        """Send every PENDING email for the lead.

        Send failures are recorded on the EmailEvent and logged, never raised.
        Events that are already SENT or FAILED are left alone, so calling this
        twice does not send anything twice.
        """
        with self._session_factory() as session:
            leads = LeadDataAccess(session)
            events = EmailEventDataAccess(session)

            lead = leads.get_by_id(lead_id)
            if lead is None:
                logger.error("Cannot send emails: lead %s not found", lead_id)
                return

            for event in events.list_pending_by_lead(lead_id):
                self._send_and_record(event, self._build_message(lead, event))
                events.commit()

    def _send_and_record(self, event: EmailEvent, message: EmailMessage) -> None:
        event.attempts += 1
        try:
            self._email_service.send(message)
        except Exception as exc:
            event.status = EmailStatus.FAILED
            event.last_error = str(exc)[:_MAX_ERROR_LENGTH]
            logger.exception("Email %s (%s) failed", event.id, event.kind.value)
        else:
            event.status = EmailStatus.SENT
            event.sent_at = utcnow()
            event.last_error = None

    def _build_message(self, lead: Lead, event: EmailEvent) -> EmailMessage:
        first = _single_line(lead.first_name)
        full_name = _single_line(f"{lead.first_name} {lead.last_name}")

        if event.kind == EmailKind.PROSPECT_CONFIRMATION:
            return EmailMessage(
                sender=self._sender,
                to=event.recipient,
                subject=_single_line(f"We received your application, {first}"),
                body=(
                    f"Hi {first},\n\n"
                    "Thank you for your interest. We have received your "
                    "application and an attorney will be in touch soon.\n"
                ),
            )

        lead_url = f"{self._frontend_url}/internal/leads/{lead.id}"
        return EmailMessage(
            sender=self._sender,
            to=event.recipient,
            subject=_single_line(f"New lead: {full_name}"),
            body=(
                "A new lead has been submitted.\n\n"
                f"Name: {full_name}\n"
                f"Email: {lead.email}\n\n"
                f"View the lead (and resume) after signing in: {lead_url}\n"
            ),
        )
