import os
import re
import uuid
from pathlib import Path
from typing import BinaryIO

from app.storage.resume_storage import ResumeNotFoundError, ResumeStorage
from app.storage.resume_validation import validate_resume

_KEY_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.(pdf|doc|docx)$"
)


class LocalResumeStorage(ResumeStorage):
    def __init__(self, directory: str | Path, max_bytes: int) -> None:
        self._directory = Path(directory)
        self._max_bytes = max_bytes
        self._directory.mkdir(parents=True, exist_ok=True)
        # Resumes are personal data: readable by the app's user only.
        os.chmod(self._directory, 0o700)

    def save(self, stream: BinaryIO) -> str:
        # Read one byte past the limit so an oversize upload is rejected
        # without buffering all of it.
        data = stream.read(self._max_bytes + 1)
        extension = validate_resume(data, self._max_bytes)
        key = f"{uuid.uuid4()}{extension}"
        path = self._directory / key
        # Exclusive create with owner-only permissions; never overwrites.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "wb") as file:
                file.write(data)
        except BaseException:
            # Do not leave a partial file behind (for example, disk full).
            path.unlink(missing_ok=True)
            raise
        return key

    def open(self, key: str) -> BinaryIO:
        path = self._path_for(key)
        if not path.is_file():
            raise ResumeNotFoundError(key)
        return path.open("rb")

    def delete(self, key: str) -> None:
        self._path_for(key).unlink(missing_ok=True)

    def _path_for(self, key: str) -> Path:
        # Only keys we generated are accepted, which rules out path traversal.
        if not _KEY_PATTERN.fullmatch(key):
            raise ResumeNotFoundError(key)
        return self._directory / key
