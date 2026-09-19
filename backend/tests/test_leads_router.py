from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.auth import get_current_attorney
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.dependencies import get_lead_email_service, get_resume_storage
from app.core.rate_limit import RateLimiter, get_submission_limiter
from app.data_acceses.email_event_data_access import EmailEventDataAccess
from app.data_acceses.lead_data_access import LeadDataAccess
from app.main import app
from app.models import Base, EmailStatus, LeadState
from app.services.lead_email_service import LeadEmailService
from app.storage.local_resume_storage import LocalResumeStorage
from tests.fakes import FakeEmailService

MAX_BYTES = 1024
ATTORNEYS = ["one@firm.example", "two@firm.example"]
PDF = b"%PDF-1.7\n%%EOF\n"


@dataclass
class Env:
    client: TestClient
    session_factory: sessionmaker[Session]
    email: FakeEmailService
    resume_dir: Path
    login: Callable[[str], None]

    def lead_count(self) -> int:
        with self.session_factory() as session:
            return LeadDataAccess(session).count()

    def stored_resumes(self) -> list[Path]:
        return list(self.resume_dir.iterdir()) if self.resume_dir.exists() else []


@pytest.fixture
def env(tmp_path: Path) -> Iterator[Env]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(engine, expire_on_commit=False)
    resume_dir = tmp_path / "resumes"
    fake_email = FakeEmailService()
    settings = Settings(
        _env_file=None,
        database_url="sqlite://",
        frontend_origin="http://localhost:3000",
        resume_storage_dir=str(resume_dir),
        resume_max_bytes=MAX_BYTES,
        google_client_id="test",
        attorney_emails=",".join(ATTORNEYS),
        email_from="no-reply@firm.example",
    )

    def override_db() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_settings] = lambda: settings
    generous = RateLimiter(max_requests=10_000, window_seconds=60)
    app.dependency_overrides[get_submission_limiter] = lambda: generous
    app.dependency_overrides[get_resume_storage] = lambda: LocalResumeStorage(
        resume_dir, MAX_BYTES
    )
    app.dependency_overrides[get_lead_email_service] = lambda: LeadEmailService(
        session_factory, fake_email, settings.email_from, settings.frontend_origin
    )

    def login(email: str) -> None:
        app.dependency_overrides[get_current_attorney] = lambda: email

    yield Env(TestClient(app), session_factory, fake_email, resume_dir, login)
    app.dependency_overrides.clear()


def submit(env: Env, omit: tuple[str, ...] = (), **overrides):
    """POST a lead; `omit` drops form fields, `overrides` replaces them."""
    fields = {
        "first_name": "Ada",
        "last_name": "Lovelace",
        "email": "ada@example.com",
        **{k: v for k, v in overrides.items() if k in ("first_name", "last_name", "email", "website")},
    }
    for name in omit:
        fields.pop(name, None)
    files = None
    if "resume" not in omit:
        files = {
            "resume": (
                overrides.get("filename", "cv.pdf"),
                overrides.get("content", PDF),
                overrides.get("content_type", "application/pdf"),
            )
        }
    return env.client.post("/api/leads", data=fields, files=files)


def create_lead(env: Env, email: str = "ada@example.com") -> str:
    response = submit(env, email=email)
    assert response.status_code == 201
    return response.json()["id"]


# POST /api/leads: happy path


def test_public_submission_creates_a_lead_and_sends_the_emails(env: Env) -> None:
    response = submit(env)

    assert response.status_code == 201
    assert set(response.json()) == {"id"}
    lead_id = response.json()["id"]
    with env.session_factory() as session:
        lead = LeadDataAccess(session).get_by_id(lead_id)
        events = EmailEventDataAccess(session).list_by_lead(lead_id)
    assert lead is not None and lead.state == LeadState.PENDING
    assert len(env.stored_resumes()) == 1
    assert sorted(m.to for m in env.email.sent) == sorted(["ada@example.com", *ATTORNEYS])
    assert {e.status for e in events} == {EmailStatus.SENT}


# POST /api/leads: honeypot


def test_filled_honeypot_is_accepted_but_discarded(env: Env) -> None:
    response = submit(env, website="http://spam.example")

    assert response.status_code == 201
    assert set(response.json()) == {"id"}
    assert env.lead_count() == 0
    assert env.stored_resumes() == []
    assert env.email.sent == []


def test_blank_honeypot_is_treated_as_empty(env: Env) -> None:
    assert submit(env, website="   ").status_code == 201
    assert env.lead_count() == 1


# POST /api/leads: invalid input


@pytest.mark.parametrize(
    "kwargs",
    [
        {"omit": ("first_name",)},
        {"omit": ("last_name",)},
        {"omit": ("email",)},
        {"omit": ("resume",)},
        {"email": "not-an-email"},
        {"first_name": "   "},
        {"last_name": ""},
    ],
    ids=[
        "no-first-name",
        "no-last-name",
        "no-email",
        "no-resume",
        "bad-email",
        "blank-first-name",
        "empty-last-name",
    ],
)
def test_invalid_submission_is_rejected_with_422_and_stores_nothing(
    env: Env, kwargs: dict
) -> None:
    response = submit(env, **kwargs)

    assert response.status_code == 422
    assert env.lead_count() == 0
    assert env.stored_resumes() == []
    assert env.email.sent == []


@pytest.mark.parametrize(
    ("kwargs", "status_code"),
    [
        ({"content": b""}, 422),
        ({"content": PDF.ljust(MAX_BYTES + 1, b"0")}, 413),
        ({"content": b"plain text", "filename": "cv.txt", "content_type": "text/plain"}, 415),
        # Claims to be a PDF by name and Content-Type, but the bytes say otherwise.
        ({"content": b"plain text", "filename": "cv.pdf", "content_type": "application/pdf"}, 415),
    ],
    ids=["empty", "oversize", "wrong-type", "spoofed-type"],
)
def test_bad_resume_maps_to_the_right_status_and_stores_nothing(
    env: Env, kwargs: dict, status_code: int
) -> None:
    response = submit(env, **kwargs)

    assert response.status_code == status_code
    assert "detail" in response.json()
    assert env.lead_count() == 0
    assert env.stored_resumes() == []
    assert env.email.sent == []


# Internal endpoints require auth (always 401 until real auth exists)


@pytest.mark.parametrize(
    ("method", "path", "json"),
    [
        ("get", "/api/leads", None),
        ("get", "/api/leads/some-id", None),
        ("get", "/api/leads/some-id/resume", None),
        ("patch", "/api/leads/some-id", {"state": "REACHED_OUT"}),
    ],
    ids=["list", "get", "resume", "patch"],
)
def test_internal_endpoints_return_401_without_authentication(
    env: Env, method: str, path: str, json: dict | None
) -> None:
    response = env.client.request(method, path, json=json)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_unauthenticated_patch_does_not_change_the_lead(env: Env) -> None:
    lead_id = create_lead(env)

    env.client.patch(f"/api/leads/{lead_id}", json={"state": "REACHED_OUT"})

    env.login(ATTORNEYS[0])
    assert env.client.get(f"/api/leads/{lead_id}").json()["state"] == "PENDING"


# GET /api/leads


def test_list_returns_newest_first_with_total_and_hides_the_resume_path(env: Env) -> None:
    env.login(ATTORNEYS[0])
    first = create_lead(env, "first@example.com")
    second = create_lead(env, "second@example.com")

    body = env.client.get("/api/leads").json()

    assert [item["id"] for item in body["items"]] == [second, first]
    assert (body["total"], body["page"], body["page_size"]) == (2, 1, 20)
    assert "resume_path" not in body["items"][0]


def test_list_filters_by_state_and_paginates(env: Env) -> None:
    env.login(ATTORNEYS[0])
    first = create_lead(env, "first@example.com")
    create_lead(env, "second@example.com")
    env.client.patch(f"/api/leads/{first}", json={"state": "REACHED_OUT"})

    reached = env.client.get("/api/leads", params={"state": "REACHED_OUT"}).json()
    page_two = env.client.get("/api/leads", params={"page_size": 1, "page": 2}).json()

    assert [i["id"] for i in reached["items"]] == [first]
    assert reached["total"] == 1
    assert len(page_two["items"]) == 1 and page_two["total"] == 2


@pytest.mark.parametrize(
    "params",
    [{"state": "BOGUS"}, {"page": 0}, {"page_size": 0}, {"page_size": 101}],
    ids=["bad-state", "page-zero", "page-size-zero", "page-size-too-big"],
)
def test_list_rejects_invalid_query_parameters(env: Env, params: dict) -> None:
    env.login(ATTORNEYS[0])
    assert env.client.get("/api/leads", params=params).status_code == 422


# GET /api/leads/{id}


def test_get_lead_returns_it(env: Env) -> None:
    env.login(ATTORNEYS[0])
    lead_id = create_lead(env)

    response = env.client.get(f"/api/leads/{lead_id}")

    assert response.status_code == 200
    assert response.json()["email"] == "ada@example.com"
    assert "resume_path" not in response.json()


def test_get_unknown_lead_returns_404(env: Env) -> None:
    env.login(ATTORNEYS[0])
    assert env.client.get("/api/leads/missing").status_code == 404


# PATCH /api/leads/{id}


def test_patch_marks_reached_out_using_the_authenticated_attorney(env: Env) -> None:
    env.login(ATTORNEYS[1])
    lead_id = create_lead(env)

    response = env.client.patch(f"/api/leads/{lead_id}", json={"state": "REACHED_OUT"})

    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "REACHED_OUT"
    assert body["reached_out_by"] == ATTORNEYS[1]
    assert body["reached_out_at"] is not None
    assert env.client.get(f"/api/leads/{lead_id}").json()["state"] == "REACHED_OUT"


def test_patch_rejects_an_identity_in_the_body_and_changes_nothing(env: Env) -> None:
    env.login(ATTORNEYS[0])
    lead_id = create_lead(env)

    response = env.client.patch(
        f"/api/leads/{lead_id}",
        json={"state": "REACHED_OUT", "reached_out_by": "someone-else@example.com"},
    )

    assert response.status_code == 422
    assert env.client.get(f"/api/leads/{lead_id}").json()["state"] == "PENDING"


@pytest.mark.parametrize(
    "body", [{"state": "PENDING"}, {"state": "BOGUS"}, {}], ids=["pending", "bogus", "empty"]
)
def test_patch_rejects_invalid_bodies(env: Env, body: dict) -> None:
    env.login(ATTORNEYS[0])
    lead_id = create_lead(env)

    assert env.client.patch(f"/api/leads/{lead_id}", json=body).status_code == 422
    assert env.client.get(f"/api/leads/{lead_id}").json()["state"] == "PENDING"


def test_patch_unknown_lead_returns_404(env: Env) -> None:
    env.login(ATTORNEYS[0])
    response = env.client.patch("/api/leads/missing", json={"state": "REACHED_OUT"})
    assert response.status_code == 404


def test_patch_twice_returns_409_and_keeps_the_first_attorney(env: Env) -> None:
    lead_id = create_lead(env)
    env.login(ATTORNEYS[0])
    env.client.patch(f"/api/leads/{lead_id}", json={"state": "REACHED_OUT"})

    env.login(ATTORNEYS[1])
    response = env.client.patch(f"/api/leads/{lead_id}", json={"state": "REACHED_OUT"})

    assert response.status_code == 409
    assert env.client.get(f"/api/leads/{lead_id}").json()["reached_out_by"] == ATTORNEYS[0]


# GET /api/leads/{id}/resume


def test_resume_download_streams_the_file_with_a_safe_header(env: Env) -> None:
    env.login(ATTORNEYS[0])
    lead_id = submit(env, filename="My CV (final).pdf").json()["id"]

    response = env.client.get(f"/api/leads/{lead_id}/resume")

    assert response.status_code == 200
    assert response.content == PDF
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"].startswith('attachment; filename="My CV (final).pdf"')
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "no-store" in response.headers["cache-control"]


def test_resume_download_neutralises_a_hostile_filename(env: Env) -> None:
    env.login(ATTORNEYS[0])
    lead_id = submit(env, filename="../../etc/pass;wd.pdf").json()["id"]

    header = env.client.get(f"/api/leads/{lead_id}/resume").headers["content-disposition"]

    assert "/" not in header.split("filename*=")[0].replace("attachment; ", "")
    assert ".." not in header
    assert header.startswith('attachment; filename="passwd.pdf"')


def test_resume_download_for_an_unknown_lead_returns_404(env: Env) -> None:
    env.login(ATTORNEYS[0])
    assert env.client.get("/api/leads/missing/resume").status_code == 404


def test_resume_download_returns_404_when_the_file_is_missing(env: Env) -> None:
    env.login(ATTORNEYS[0])
    lead_id = create_lead(env)
    for path in env.stored_resumes():
        path.unlink()

    response = env.client.get(f"/api/leads/{lead_id}/resume")

    assert response.status_code == 404
    assert "detail" in response.json()


def test_resume_download_without_authentication_returns_no_file(env: Env) -> None:
    lead_id = create_lead(env)

    response = env.client.get(f"/api/leads/{lead_id}/resume")

    assert response.status_code == 401
    assert PDF not in response.content


# Timestamps


def test_lead_timestamps_are_serialised_as_utc(env: Env) -> None:
    env.login(ATTORNEYS[0])
    lead_id = create_lead(env)
    env.client.patch(f"/api/leads/{lead_id}", json={"state": "REACHED_OUT"})

    body = env.client.get(f"/api/leads/{lead_id}").json()

    for field in ("created_at", "reached_out_at"):
        assert body[field].endswith(("Z", "+00:00")), body[field]


# Error responses do not expose internal values


def test_a_missing_resume_file_does_not_reveal_the_stored_file_name(env: Env) -> None:
    env.login(ATTORNEYS[0])
    lead_id = create_lead(env)
    stored_name = env.stored_resumes()[0].name
    for path in env.stored_resumes():
        path.unlink()

    response = env.client.get(f"/api/leads/{lead_id}/resume")

    assert response.status_code == 404
    assert response.json() == {"detail": "Resume file not found"}
    assert stored_name not in response.text


def test_an_unknown_lead_gets_a_generic_message(env: Env) -> None:
    env.login(ATTORNEYS[0])
    response = env.client.get("/api/leads/some-made-up-id")

    assert response.status_code == 404
    assert response.json() == {"detail": "Lead not found"}
