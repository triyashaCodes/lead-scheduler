import pytest
from fastapi.testclient import TestClient

from app.core.rate_limit import RateLimiter, get_submission_limiter
from app.main import app

PDF = b"%PDF-1.7\n%%EOF\n"


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_requests_up_to_the_limit_are_allowed_then_blocked() -> None:
    limiter = RateLimiter(3, 60, clock=Clock())

    assert [limiter.check("a") for _ in range(3)] == [None, None, None]
    assert limiter.check("a") is not None


def test_the_wait_time_counts_down_to_the_oldest_request_leaving_the_window() -> None:
    clock = Clock()
    limiter = RateLimiter(1, 60, clock=clock)
    limiter.check("a")

    clock.now += 20

    assert limiter.check("a") == 40


def test_the_window_slides_so_old_requests_stop_counting() -> None:
    clock = Clock()
    limiter = RateLimiter(2, 60, clock=clock)
    limiter.check("a")
    limiter.check("a")
    assert limiter.check("a") is not None

    clock.now += 61

    assert limiter.check("a") is None


def test_each_client_has_its_own_allowance() -> None:
    limiter = RateLimiter(1, 60, clock=Clock())

    assert limiter.check("a") is None
    assert limiter.check("a") is not None
    assert limiter.check("b") is None


def test_memory_stays_bounded_when_many_addresses_appear() -> None:
    limiter = RateLimiter(5, 60, clock=Clock(), max_keys=50)

    for n in range(500):
        limiter.check(f"10.0.{n // 250}.{n % 250}")

    assert len(limiter._hits) <= 50


@pytest.fixture
def small_limit():
    limiter = RateLimiter(max_requests=3, window_seconds=3600)
    app.dependency_overrides[get_submission_limiter] = lambda: limiter
    yield limiter
    app.dependency_overrides.pop(get_submission_limiter, None)


def submit(client: TestClient):
    # An invalid form is enough: the limit is checked before anything else.
    return client.post("/api/leads", data={"first_name": "A"})


def test_the_public_form_returns_429_with_retry_after_once_the_limit_is_hit(small_limit) -> None:
    client = TestClient(app, client=("203.0.113.7", 5000))

    statuses = [submit(client).status_code for _ in range(3)]
    blocked = submit(client)

    assert 429 not in statuses
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) >= 1
    assert blocked.json() == {"detail": "Too many submissions. Try again later."}


def test_another_address_is_not_affected(small_limit) -> None:
    first = TestClient(app, client=("203.0.113.7", 5000))
    second = TestClient(app, client=("198.51.100.9", 5000))
    for _ in range(4):
        submit(first)

    assert submit(first).status_code == 429
    assert submit(second).status_code != 429


def test_attorney_endpoints_are_not_rate_limited_by_the_form_limit(small_limit) -> None:
    client = TestClient(app, client=("203.0.113.7", 5000))
    for _ in range(5):
        submit(client)

    # Still 401 (needs auth), not 429.
    assert client.get("/api/leads").status_code == 401
