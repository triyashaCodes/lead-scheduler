import io
import zipfile

from app.storage.resume_storage import (
    EmptyResumeError,
    ResumeTooLargeError,
    UnsupportedResumeTypeError,
)

_PDF_MAGIC = b"%PDF-"
_OLE_MAGIC = bytes.fromhex("D0CF11E0A1B11AE1")
_ZIP_MAGIC = b"PK\x03\x04"
_DOC_STREAM_NAME = "WordDocument".encode("utf-16-le")
_DOCX_MARKER = "word/document.xml"


def detect_extension(data: bytes) -> str | None:
    """Return ".pdf", ".doc" or ".docx" based on file content, else None.

    Legacy .doc and Office Open XML share containers with other Office formats
    (OLE for .xls/.ppt, ZIP for .xlsx/.pptx/.jar), so the container magic alone
    is not enough: we also look for the Word-specific stream or part.
    """
    if data.startswith(_PDF_MAGIC):
        return ".pdf"
    if data.startswith(_OLE_MAGIC):
        return ".doc" if _DOC_STREAM_NAME in data else None
    if data.startswith(_ZIP_MAGIC):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                return ".docx" if _DOCX_MARKER in archive.namelist() else None
        except zipfile.BadZipFile:
            return None
    return None


def validate_resume(data: bytes, max_bytes: int) -> str:
    """Check size and type, returning the extension for the detected type."""
    if not data:
        raise EmptyResumeError("Resume file is empty")
    if len(data) > max_bytes:
        raise ResumeTooLargeError(max_bytes)
    extension = detect_extension(data)
    if extension is None:
        raise UnsupportedResumeTypeError()
    return extension
