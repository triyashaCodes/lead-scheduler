from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import SessionLocal, get_db
from app.data_acceses.email_event_data_access import EmailEventDataAccess
from app.data_acceses.lead_data_access import LeadDataAccess
from app.services.email_service import build_email_service
from app.services.lead_email_service import LeadEmailService
from app.services.lead_service import LeadService
from app.storage.local_resume_storage import LocalResumeStorage
from app.storage.resume_storage import ResumeStorage


def get_lead_data_access(db: Annotated[Session, Depends(get_db)]) -> LeadDataAccess:
    return LeadDataAccess(db)


def get_email_event_data_access(
    db: Annotated[Session, Depends(get_db)],
) -> EmailEventDataAccess:
    return EmailEventDataAccess(db)


def get_resume_storage(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ResumeStorage:
    return LocalResumeStorage(settings.resume_storage_dir, settings.resume_max_bytes)


def get_lead_service(
    settings: Annotated[Settings, Depends(get_settings)],
    lead_data_access: Annotated[LeadDataAccess, Depends(get_lead_data_access)],
    email_event_data_access: Annotated[
        EmailEventDataAccess, Depends(get_email_event_data_access)
    ],
    resume_storage: Annotated[ResumeStorage, Depends(get_resume_storage)],
) -> LeadService:
    return LeadService(
        lead_data_access,
        resume_storage,
        email_event_data_access,
        settings.attorney_email_list,
    )


def get_lead_email_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> LeadEmailService:
    # Opens its own sessions, so it does not depend on the request's session.
    return LeadEmailService(
        session_factory=SessionLocal,
        email_service=build_email_service(settings),
        sender=settings.email_from,
        frontend_url=settings.frontend_origin,
    )
