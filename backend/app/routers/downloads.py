import re
from urllib.parse import quote

_UNSAFE_CHARS = re.compile(r'[\x00-\x1f\x7f"\\/;:*?<>|]')
_NON_ASCII_SAFE = re.compile(r"[^A-Za-z0-9._ ()-]")
_MAX_STEM_LENGTH = 100


def content_disposition(original_name: str | None, extension: str) -> str:
    """Build an attachment header from an untrusted client filename.

    Only the name's text survives: directories, quotes, control characters and
    header separators are removed, and the extension always comes from the
    stored file type, never from the client.
    """
    base = re.split(r"[\\/]", original_name or "")[-1]
    stem = base.rsplit(".", 1)[0] if "." in base else base
    stem = _UNSAFE_CHARS.sub("", stem)
    stem = " ".join(stem.split()).strip(" .")[:_MAX_STEM_LENGTH].strip(" .")
    filename = f"{stem or 'resume'}{extension}"

    ascii_name = _NON_ASCII_SAFE.sub("_", filename)
    return (
        f'attachment; filename="{ascii_name}"; '
        f"filename*=UTF-8''{quote(filename, safe='')}"
    )
