from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.core.body_limit import BodySizeLimitMiddleware
from app.main import app as real_app

LIMIT = 100


def make_client() -> tuple[TestClient, list[int]]:
    app = FastAPI()
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=LIMIT)
    handled: list[int] = []

    @app.post("/echo")
    async def echo(request: Request) -> dict:
        body = await request.body()
        handled.append(len(body))
        return {"size": len(body)}

    return TestClient(app), handled


def test_a_body_within_the_limit_is_accepted() -> None:
    client, handled = make_client()
    assert client.post("/echo", content=b"x" * LIMIT).json() == {"size": LIMIT}
    assert handled == [LIMIT]


def test_a_declared_oversize_body_is_refused_without_reaching_the_handler() -> None:
    client, handled = make_client()

    response = client.post("/echo", content=b"x" * (LIMIT + 1))

    assert response.status_code == 413
    assert handled == []


def test_a_chunked_body_with_no_declared_length_is_stopped_at_the_limit() -> None:
    client, handled = make_client()

    def chunks():
        for _ in range(10):
            yield b"x" * 30  # 300 bytes in total, no Content-Length

    response = client.post("/echo", content=chunks())

    assert response.status_code == 413
    assert handled == []


def test_the_real_app_refuses_an_oversize_lead_submission(monkeypatch) -> None:
    limit = 1024 + 64 * 1024  # RESUME_MAX_BYTES from the test env, plus overhead
    client = TestClient(real_app)

    response = client.post(
        "/api/leads",
        data={"first_name": "A", "last_name": "B", "email": "a@example.com"},
        files={"resume": ("cv.pdf", b"%PDF-" + b"0" * (limit + 10), "application/pdf")},
    )

    assert response.status_code == 413
    assert response.json() == {"detail": "Request body is too large"}


def test_the_413_carries_cors_headers_so_the_browser_can_read_it() -> None:
    client = TestClient(real_app)

    response = client.post(
        "/api/leads",
        data={"first_name": "A"},
        files={"resume": ("cv.pdf", b"0" * (70 * 1024), "application/pdf")},
        headers={"Origin": "http://localhost:3000"},
    )

    assert response.status_code == 413
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
