from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.services.lead_exceptions import (
    InvalidStateTransitionError,
    LeadNotFoundError,
)
from app.storage.resume_storage import (
    EmptyResumeError,
    ResumeTooLargeError,
    UnsupportedResumeTypeError,
)

_STATUS_BY_ERROR: dict[type[Exception], int] = {
    LeadNotFoundError: status.HTTP_404_NOT_FOUND,
    InvalidStateTransitionError: status.HTTP_409_CONFLICT,
    EmptyResumeError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    ResumeTooLargeError: status.HTTP_413_CONTENT_TOO_LARGE,
    UnsupportedResumeTypeError: status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
}


def register_error_handlers(app: FastAPI) -> None:
    """Map domain exceptions to HTTP responses; services never see HTTP."""
    for error_type, status_code in _STATUS_BY_ERROR.items():
        app.add_exception_handler(error_type, _make_handler(status_code))


def _make_handler(status_code: int):
    async def handler(_: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=status_code, content={"detail": str(exc)})

    return handler
