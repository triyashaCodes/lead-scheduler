from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.services.lead_exceptions import (
    InvalidStateTransitionError,
    LeadNotFoundError,
)
from app.storage.resume_storage import (
    EmptyResumeError,
    ResumeNotFoundError,
    ResumeTooLargeError,
    UnsupportedResumeTypeError,
)

_STATUS_BY_ERROR: dict[type[Exception], int] = {
    LeadNotFoundError: status.HTTP_404_NOT_FOUND,
    ResumeNotFoundError: status.HTTP_404_NOT_FOUND,
    InvalidStateTransitionError: status.HTTP_409_CONFLICT,
    EmptyResumeError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    ResumeTooLargeError: status.HTTP_413_CONTENT_TOO_LARGE,
    UnsupportedResumeTypeError: status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
}


# What the client sees for these errors. The exception text can contain internal
# values such as the stored file name, so it is never sent.
_PUBLIC_MESSAGES: dict[type[Exception], str] = {
    LeadNotFoundError: "Lead not found",
    ResumeNotFoundError: "Resume file not found",
}


def register_error_handlers(app: FastAPI) -> None:
    """Map domain exceptions to HTTP responses; services never see HTTP."""
    for error_type, status_code in _STATUS_BY_ERROR.items():
        app.add_exception_handler(
            error_type, _make_handler(status_code, _PUBLIC_MESSAGES.get(error_type))
        )


def _make_handler(status_code: int, message: str | None):
    async def handler(_: Request, exc: Exception) -> JSONResponse:
        detail = message if message is not None else str(exc)
        return JSONResponse(status_code=status_code, content={"detail": detail})

    return handler
