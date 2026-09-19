import pytest

from app.routers.downloads import content_disposition


def test_plain_name_gets_the_stored_extension() -> None:
    header = content_disposition("Ada Lovelace CV.pdf", ".pdf")
    assert header == (
        'attachment; filename="Ada Lovelace CV.pdf"; '
        "filename*=UTF-8''Ada%20Lovelace%20CV.pdf"
    )


@pytest.mark.parametrize(
    ("original", "expected"),
    [
        ("../../etc/passwd.pdf", "passwd.pdf"),
        ("C:\\Users\\ada\\cv.pdf", "cv.pdf"),
        ('a"b;c.pdf', "abc.pdf"),
        ("evil\r\nSet-Cookie: x=1.pdf", "evilSet-Cookie x_1.pdf"),
        ("cv.exe", "cv.pdf"),
        ("cv", "cv.pdf"),
        (".pdf", "resume.pdf"),
        ("...", "resume.pdf"),
        ("", "resume.pdf"),
        (None, "resume.pdf"),
    ],
)
def test_untrusted_names_are_reduced_to_safe_text(original: str | None, expected: str) -> None:
    header = content_disposition(original, ".pdf")
    assert header.startswith(f'attachment; filename="{expected}"')
    assert "\r" not in header and "\n" not in header
    assert "/" not in header.split("filename*=")[0]


def test_non_ascii_names_use_an_ascii_fallback_and_utf8_form() -> None:
    header = content_disposition("Renée Müller.docx", ".docx")
    assert 'filename="Ren_e M_ller.docx"' in header
    assert "filename*=UTF-8''Ren%C3%A9e%20M%C3%BCller.docx" in header


def test_very_long_names_are_truncated() -> None:
    header = content_disposition("a" * 500 + ".pdf", ".pdf")
    assert len(header) < 300
    assert header.startswith('attachment; filename="' + "a" * 100 + '.pdf"')
