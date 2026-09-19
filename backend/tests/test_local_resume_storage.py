import io
import os
import stat
import re
import zipfile
from pathlib import Path

import pytest

from app.storage.local_resume_storage import LocalResumeStorage
from app.storage.resume_storage import (
    EmptyResumeError,
    ResumeNotFoundError,
    ResumeTooLargeError,
    UnsupportedResumeTypeError,
)

MAX_BYTES = 1024
UUID_KEY = re.compile(r"^[0-9a-f-]{36}\.(pdf|doc|docx)$")

OLE_MAGIC = bytes.fromhex("D0CF11E0A1B11AE1")


def make_pdf() -> bytes:
    return b"%PDF-1.7\n%%EOF\n"


def make_doc() -> bytes:
    return OLE_MAGIC + b"\x00" * 32 + "WordDocument".encode("utf-16-le")


def make_zip(*names: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name in names:
            archive.writestr(name, "<x/>")
    return buffer.getvalue()


def make_docx() -> bytes:
    return make_zip("[Content_Types].xml", "word/document.xml")


@pytest.fixture
def storage(tmp_path: Path) -> LocalResumeStorage:
    return LocalResumeStorage(tmp_path / "resumes", max_bytes=MAX_BYTES)


def stored_files(storage: LocalResumeStorage) -> list[Path]:
    return list(storage._directory.iterdir())


@pytest.mark.parametrize(
    ("content", "extension"),
    [(make_pdf(), ".pdf"), (make_doc(), ".doc"), (make_docx(), ".docx")],
)
def test_save_stores_under_generated_name_with_detected_extension(
    storage: LocalResumeStorage, content: bytes, extension: str
) -> None:
    key = storage.save(io.BytesIO(content))

    assert UUID_KEY.match(key)
    assert key.endswith(extension)
    assert [f.name for f in stored_files(storage)] == [key]
    with storage.open(key) as stored:
        assert stored.read() == content


def test_save_accepts_a_file_exactly_at_the_limit(storage: LocalResumeStorage) -> None:
    content = make_pdf().ljust(MAX_BYTES, b"0")
    assert storage.save(io.BytesIO(content))


def test_save_rejects_empty_file(storage: LocalResumeStorage) -> None:
    with pytest.raises(EmptyResumeError):
        storage.save(io.BytesIO(b""))
    assert stored_files(storage) == []


def test_save_rejects_oversize_file(storage: LocalResumeStorage) -> None:
    content = make_pdf().ljust(MAX_BYTES + 1, b"0")
    with pytest.raises(ResumeTooLargeError):
        storage.save(io.BytesIO(content))
    assert stored_files(storage) == []


@pytest.mark.parametrize(
    "content",
    [
        b"just some text",
        b"\x89PNG\r\n\x1a\n" + b"0" * 16,
        # Right containers, wrong Office format:
        OLE_MAGIC + b"\x00" * 32 + "Workbook".encode("utf-16-le"),
        make_zip("[Content_Types].xml", "xl/workbook.xml"),
        b"PK\x03\x04 not really a zip",
    ],
    ids=["text", "png", "xls-like", "xlsx-like", "corrupt-zip"],
)
def test_save_rejects_unsupported_content(
    storage: LocalResumeStorage, content: bytes
) -> None:
    with pytest.raises(UnsupportedResumeTypeError):
        storage.save(io.BytesIO(content))
    assert stored_files(storage) == []


def test_open_and_delete_reject_keys_that_are_not_generated_names(
    storage: LocalResumeStorage,
) -> None:
    for bad_key in ["../secret.pdf", "/etc/passwd", "resume.pdf", ""]:
        with pytest.raises(ResumeNotFoundError):
            storage.open(bad_key)
        with pytest.raises(ResumeNotFoundError):
            storage.delete(bad_key)


def test_open_missing_raises_and_delete_missing_is_a_noop(
    storage: LocalResumeStorage,
) -> None:
    missing = "00000000-0000-0000-0000-000000000000.pdf"
    with pytest.raises(ResumeNotFoundError):
        storage.open(missing)
    storage.delete(missing)


def test_delete_removes_the_file(storage: LocalResumeStorage) -> None:
    key = storage.save(io.BytesIO(make_pdf()))
    storage.delete(key)
    assert stored_files(storage) == []


# File permissions and failed writes


@pytest.mark.skipif(os.name != "posix", reason="POSIX permissions")
def test_resume_files_and_directory_are_private_to_the_owner(
    storage: LocalResumeStorage,
) -> None:
    key = storage.save(io.BytesIO(make_pdf()))

    assert stat.S_IMODE(os.stat(storage._directory).st_mode) == 0o700
    assert stat.S_IMODE(os.stat(storage._directory / key).st_mode) == 0o600


@pytest.mark.skipif(os.name != "posix", reason="POSIX permissions")
def test_an_existing_world_readable_directory_is_tightened(tmp_path: Path) -> None:
    directory = tmp_path / "resumes"
    directory.mkdir(mode=0o755)

    LocalResumeStorage(directory, max_bytes=MAX_BYTES)

    assert stat.S_IMODE(os.stat(directory).st_mode) == 0o700


def test_a_failed_write_leaves_no_partial_file(
    storage: LocalResumeStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_fdopen = os.fdopen

    class FailingFile:
        def __init__(self, fd: int) -> None:
            self._file = real_fdopen(fd, "wb")

        def __enter__(self) -> "FailingFile":
            return self

        def __exit__(self, *exc: object) -> None:
            self._file.close()

        def write(self, data: bytes) -> int:
            raise OSError("disk full")

    monkeypatch.setattr(os, "fdopen", lambda fd, mode: FailingFile(fd))

    with pytest.raises(OSError, match="disk full"):
        storage.save(io.BytesIO(make_pdf()))

    assert stored_files(storage) == []
