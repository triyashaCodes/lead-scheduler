import uuid
from collections.abc import Iterator
from typing import Annotated, BinaryIO

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Query, UploadFile, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from app.core.auth import get_current_attorney
from app.core.config import Settings, get_settings
from app.core.dependencies import get_lead_email_service, get_lead_service
from app.models import LeadState
from app.routers.downloads import content_disposition
from app.schemas.lead import (
    LeadCreate,
    LeadCreated,
    LeadList,
    LeadRead,
    LeadUpdate,
)
from app.services.lead_email_service import LeadEmailService
from app.services.lead_service import LeadService

router = APIRouter(prefix="/leads", tags=["leads"])

LeadServiceDep = Annotated[LeadService, Depends(get_lead_service)]
AttorneyDep = Annotated[str, Depends(get_current_attorney)]


@router.post("", response_model=LeadCreated, status_code=status.HTTP_201_CREATED)
def create_lead(
    first_name: Annotated[str, Form()],
    last_name: Annotated[str, Form()],
    email: Annotated[str, Form()],
    resume: UploadFile,
    background_tasks: BackgroundTasks,
    service: LeadServiceDep,
    email_service: Annotated[LeadEmailService, Depends(get_lead_email_service)],
    settings: Annotated[Settings, Depends(get_settings)],
    website: Annotated[str, Form()] = "",
) -> LeadCreated:
    # A form model cannot be combined with a file upload, so the text fields
    # are declared individually and validated by the schema here.
    try:
        data = LeadCreate(first_name=first_name, last_name=last_name, email=email)
    except ValidationError as exc:
        raise RequestValidationError(
            exc.errors(include_url=False, include_context=False)
        ) from exc
    # `website` is the honeypot: hidden from people, filled in by bots.
    # Read one byte past the limit so the service can reject oversize files
    # without the whole upload being loaded into memory.
    resume_bytes = resume.file.read(settings.resume_max_bytes + 1)
    lead = service.create_lead(
        data, resume_bytes, resume.filename or "", honeypot=website
    )
    if lead is None:
        # Look identical to a real submission so bots learn nothing.
        return LeadCreated(id=str(uuid.uuid4()))
    background_tasks.add_task(email_service.send_lead_emails, lead.id)
    return LeadCreated(id=lead.id)


@router.get("", response_model=LeadList, dependencies=[Depends(get_current_attorney)])
def list_leads(
    service: LeadServiceDep,
    state: LeadState | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> LeadList:
    leads, total = service.list_leads(
        state=state, limit=page_size, offset=(page - 1) * page_size
    )
    return LeadList(
        items=[LeadRead.model_validate(lead) for lead in leads],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{lead_id}", response_model=LeadRead, dependencies=[Depends(get_current_attorney)]
)
def get_lead(lead_id: str, service: LeadServiceDep) -> LeadRead:
    return LeadRead.model_validate(service.get_lead(lead_id))


def _stream_and_close(stream: BinaryIO, chunk_size: int = 64 * 1024) -> Iterator[bytes]:
    try:
        while chunk := stream.read(chunk_size):
            yield chunk
    finally:
        stream.close()


@router.get("/{lead_id}/resume", dependencies=[Depends(get_current_attorney)])
def download_resume(lead_id: str, service: LeadServiceDep) -> StreamingResponse:
    resume = service.open_resume(lead_id)
    return StreamingResponse(
        _stream_and_close(resume.stream),
        media_type=resume.content_type,
        headers={
            "Content-Disposition": content_disposition(
                resume.original_filename, resume.extension
            ),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.patch("/{lead_id}", response_model=LeadRead)
def update_lead(
    lead_id: str,
    update: LeadUpdate,  # only accepts state=REACHED_OUT, which is the one transition
    attorney_email: AttorneyDep,
    service: LeadServiceDep,
) -> LeadRead:
    return LeadRead.model_validate(service.mark_reached_out(lead_id, attorney_email))
