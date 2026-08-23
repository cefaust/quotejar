"""Rate limiting.

The load-bearing test in this file is
test_store_unavailable_returns_200_not_500. Fail-open is the behaviour that
cannot be observed in normal operation -- it only shows up during a DynamoDB
outage, which is the worst possible moment to discover it regressed. Getting it
wrong turns a partial outage into a total one, and nothing else in the suite
would notice.
"""

import uuid

import pytest

from app.config import settings
from app.dependencies import limiter
from app.ratelimit import RateLimiter
from tests.conftest import MemoryStore


class BrokenStore:
    """A store that is always unreachable, standing in for a DynamoDB outage.

    Raises rather than returning a sentinel, because that is what boto3 does --
    a botocore ClientError, an endpoint connection error, or an ImportError if
    the SDK is missing. The limiter must treat all of them alike.
    """

    def increment(self, key: str, window_seconds: int) -> int:
        raise ConnectionError("dynamodb unreachable")

    def get(self, key: str) -> int:
        raise ConnectionError("dynamodb unreachable")


@pytest.fixture
def memory_limiter():
    """The app's limiter, already on an in-memory store via the autouse
    isolation fixture in conftest. Named explicitly so the tests that depend on
    real counting say so."""
    return limiter


@pytest.fixture
def broken_limiter():
    original = limiter.store
    limiter.store = BrokenStore()
    yield limiter
    limiter.store = original


def _email() -> str:
    return f"{uuid.uuid4()}@example.com"


PASSWORD = "correct-horse-battery"


# --- the limiter itself ----------------------------------------------------


def test_requests_under_the_limit_are_allowed():
    rl = RateLimiter(MemoryStore())
    for _ in range(5):
        assert rl.check("scope", "id", limit=5, window_seconds=60).allowed


def test_the_limit_is_enforced():
    rl = RateLimiter(MemoryStore())
    for _ in range(5):
        rl.check("scope", "id", limit=5, window_seconds=60)

    assert not rl.check("scope", "id", limit=5, window_seconds=60).allowed


def test_one_identity_does_not_consume_anothers_quota():
    """The property that makes per-user limiting worth anything.

    If keys collided, one noisy user would throttle everybody, which is a
    self-inflicted denial of service wearing the costume of a security control.
    """
    rl = RateLimiter(MemoryStore())
    for _ in range(10):
        rl.check("scope", "noisy-user", limit=5, window_seconds=60)

    assert rl.check("scope", "quiet-user", limit=5, window_seconds=60).allowed


def test_scopes_are_independent():
    """Exhausting the IP limit must not exhaust the per-user limit."""
    rl = RateLimiter(MemoryStore())
    for _ in range(10):
        rl.check("auth-ip", "same-value", limit=5, window_seconds=60)

    assert rl.check("user", "same-value", limit=5, window_seconds=60).allowed


def test_the_window_resets(monkeypatch):
    """Quota returns once the window has passed.

    Time is advanced rather than slept: a test that waits 60 seconds is a test
    people delete.
    """
    import app.ratelimit as rlmod

    now = 1_000_000.0
    monkeypatch.setattr(rlmod.time, "time", lambda: now)

    rl = RateLimiter(MemoryStore())
    for _ in range(5):
        rl.check("scope", "id", limit=5, window_seconds=60)
    assert not rl.check("scope", "id", limit=5, window_seconds=60).allowed

    # Two windows on, so neither the current nor the previous window carries
    # any of the old count.
    now += 120
    assert rl.check("scope", "id", limit=5, window_seconds=60).allowed


def test_the_previous_window_still_counts_across_a_boundary(monkeypatch):
    """The flaw in fixed-window counting, and why this is a sliding window.

    A fixed window lets an attacker spend the whole limit at 11:59:59 and the
    whole limit again at 12:00:00 -- 2x the intended rate in two seconds, with
    both windows individually legal. Weighting the previous window by how much
    of it still overlaps means those earlier requests are still counted just
    after the boundary, and the second burst is rejected.
    """
    import app.ratelimit as rlmod

    now = 1_000_000.0 - 1  # one second before a window boundary
    monkeypatch.setattr(rlmod.time, "time", lambda: now)

    rl = RateLimiter(MemoryStore())
    for _ in range(5):
        rl.check("scope", "id", limit=5, window_seconds=60)

    now += 2  # just over the boundary: a fixed window would reset here
    assert not rl.check("scope", "id", limit=5, window_seconds=60).allowed


def test_a_decision_reports_the_remaining_quota():
    rl = RateLimiter(MemoryStore())
    first = rl.check("scope", "id", limit=5, window_seconds=60)

    assert first.limit == 5
    assert first.remaining == 4
    assert 0 < first.reset_seconds <= 60


# --- the limit means what it says ------------------------------------------


def test_peek_allows_exactly_the_limit_and_not_one_more():
    """Regression: peek() used to permit limit + 1.

    peek() decides *before* the attempt it is authorising has been recorded,
    so that attempt is not yet in the stored count and has to be added in.
    Without it the comparison runs against a total the request is missing
    from, and every peek-guarded limit sits one attempt looser than its
    configured value -- auth_email_limit = 5 allowed six failed logins.

    The failure is invisible from the outside: throttling still happens, just
    one attempt late, so nothing looks broken. Only counting catches it.
    """
    rl = RateLimiter(MemoryStore())

    permitted = 0
    while rl.peek("scope", "id", limit=5, window_seconds=60).allowed:
        rl.record("scope", "id", 60)
        permitted += 1
        if permitted > 20:  # never spin if the boundary regresses open
            break

    assert permitted == 5


def test_check_and_peek_agree_on_what_a_limit_permits():
    """The two paths must not disagree about what `limit` means.

    They count at different moments -- check() increments then decides,
    peek() decides then the caller may record -- and that difference is
    exactly where the off-by-one lived. Whatever the number, both must let the
    same quota through.
    """
    for limit in (1, 3, 5, 10):
        counted = RateLimiter(MemoryStore())
        via_check = 0
        while counted.check("scope", "id", limit, 60).allowed and via_check <= 20:
            via_check += 1

        deferred = RateLimiter(MemoryStore())
        via_peek = 0
        while deferred.peek("scope", "id", limit, 60).allowed and via_peek <= 20:
            deferred.record("scope", "id", 60)
            via_peek += 1

        assert via_check == limit, f"check allowed {via_check} against limit {limit}"
        assert via_peek == limit, f"peek allowed {via_peek} against limit {limit}"


# --- refusals must not compound --------------------------------------------


def test_a_refused_request_is_not_counted():
    """The counter records what was admitted, never what was turned away.

    Counting a refusal lets a caller inflate the very number its own future
    decisions are built from. The direct consequence is the lockout in the
    next test; the secondary one is that every rejected request would cost a
    DynamoDB write, which is also what pushes the write rate toward the
    per-partition-key throttling ceiling described in README.md.
    """
    store = MemoryStore()
    rl = RateLimiter(store)

    for _ in range(5):
        rl.check("scope", "id", limit=5, window_seconds=60)
    after_quota_spent = dict(store.counts)

    for _ in range(50):
        assert not rl.check("scope", "id", limit=5, window_seconds=60).allowed

    assert store.counts == after_quota_spent, "a refused request was counted"


def test_a_client_that_ignores_429_still_gets_its_quota_back(monkeypatch):
    """A retry loop must not push its own quota further away.

    `check` used to increment before deciding, so every rejected retry raised
    the counter that the next window's estimate is built from. A client
    retrying once a second never recovered -- "ten per fifteen minutes"
    silently became an indefinite lockout. The client that behaves this way is
    usually not an attacker but a mobile app with a naive retry loop, and its
    user has no way to find out why they are shut out for hours.

    Time is advanced rather than slept; an hour-long test is a deleted test.
    """
    import app.ratelimit as rlmod

    now = 1_000_000.0
    monkeypatch.setattr(rlmod.time, "time", lambda: now)

    store = MemoryStore()
    rl = RateLimiter(store)
    start = now

    # Spend the quota, then keep hammering through this window and the next,
    # ignoring every refusal.
    while now < start + 1800:
        rl.check("scope", "id", limit=10, window_seconds=900)
        now += 1

    # No window counter may exceed the limit: that is the invariant that
    # keeps the carry-over into the next window bounded.
    assert max(store.counts.values()) <= 10

    # A full window later the client is being served again, at close to its
    # full allowance rather than nothing at all.
    admitted = 0
    while now < start + 2700:
        if rl.check("scope", "id", limit=10, window_seconds=900).allowed:
            admitted += 1
        now += 1

    assert 8 <= admitted <= 10, f"admitted {admitted} in the window, expected ~10"


# --- fail open -------------------------------------------------------------


def test_the_limiter_allows_requests_when_the_store_is_down():
    rl = RateLimiter(BrokenStore())
    decision = rl.check("scope", "id", limit=5, window_seconds=60)

    assert decision.allowed
    assert decision.remaining == decision.limit


def test_a_broken_store_never_blocks_however_many_requests():
    """Fail-open must not degrade into fail-closed after N attempts."""
    rl = RateLimiter(BrokenStore())
    for _ in range(50):
        assert rl.check("scope", "id", limit=5, window_seconds=60).allowed


def test_recording_a_failure_does_not_raise_when_the_store_is_down():
    """record() runs after a request is handled, so raising here would turn a
    correct 401 into a 500 -- failing the user because bookkeeping failed."""
    RateLimiter(BrokenStore()).record("scope", "id", 60)


def test_store_unavailable_returns_200_not_500(broken_limiter, client, child):
    """End to end: a DynamoDB outage must not take the API down.

    The single most important assertion in this file. A limiter that fails
    closed converts a dependency outage into a total outage, and this is the
    only test that would catch that regression.
    """
    response = client.get("/quotes")

    assert response.status_code == 200


def test_login_still_works_when_the_store_is_down(broken_limiter, anon_client, db):
    email = _email()
    anon_client.post("/auth/register", json={"email": email, "password": PASSWORD})

    response = anon_client.post(
        "/auth/login", data={"username": email, "password": PASSWORD}
    )

    assert response.status_code == 200


# --- through the API -------------------------------------------------------


def test_repeated_logins_from_one_ip_are_eventually_rejected(
    memory_limiter, anon_client
):
    email = _email()
    anon_client.post("/auth/register", json={"email": email, "password": PASSWORD})

    codes = [
        anon_client.post(
            "/auth/login", data={"username": email, "password": "wrong"}
        ).status_code
        for _ in range(settings.auth_ip_limit + 3)
    ]

    assert 429 in codes, "the per-IP limit never triggered"


def test_a_429_carries_retry_after_and_ratelimit_headers(memory_limiter, anon_client):
    """A 429 with no timing is a bad citizen: it tells a client to stop without
    saying for how long, so well-behaved clients guess and the rest hammer."""
    for _ in range(settings.auth_ip_limit + 3):
        response = anon_client.post(
            "/auth/login", data={"username": _email(), "password": "wrong"}
        )
        if response.status_code == 429:
            break
    else:
        pytest.fail("never got a 429")

    assert "retry-after" in response.headers
    assert int(response.headers["retry-after"]) > 0
    assert response.headers["ratelimit-limit"] == str(settings.auth_ip_limit)
    assert response.headers["ratelimit-remaining"] == "0"
    assert int(response.headers["ratelimit-reset"]) > 0


def test_repeated_failures_against_one_email_are_limited(memory_limiter, anon_client):
    """The second axis. A botnet defeats the per-IP limit while every attempt
    still lands on one address.

    Asserts the exact boundary rather than overshooting it. An earlier version
    of this test made limit + 1 failures before checking for a 429, which
    passes whether the limit is honoured at five attempts or at six -- and it
    was six. A rate limit test that does not pin the count cannot tell a
    working limit from one that is off by one.
    """
    email = _email()
    anon_client.post("/auth/register", json={"email": email, "password": PASSWORD})

    for attempt in range(settings.auth_email_limit):
        response = anon_client.post(
            "/auth/login", data={"username": email, "password": "wrong"}
        )
        assert response.status_code == 401, f"attempt {attempt + 1} was throttled early"

    # The next one is refused, and the correct password does not buy a way out
    # -- the limit is on the address being attempted, not on the credential.
    response = anon_client.post(
        "/auth/login", data={"username": email, "password": PASSWORD}
    )
    assert response.status_code == 429


def test_the_last_attempt_inside_the_email_limit_still_works(
    memory_limiter, anon_client
):
    """The other direction: the limit must not be one attempt too strict.

    Fixing an off-by-one that ran loose is an easy way to introduce one that
    runs tight, which would lock a legitimate user out a whole attempt early.
    """
    email = _email()
    anon_client.post("/auth/register", json={"email": email, "password": PASSWORD})

    for _ in range(settings.auth_email_limit - 1):
        anon_client.post("/auth/login", data={"username": email, "password": "wrong"})

    response = anon_client.post(
        "/auth/login", data={"username": email, "password": PASSWORD}
    )
    assert response.status_code == 200


def test_successful_logins_do_not_count_against_the_email_limit(
    memory_limiter, anon_client
):
    """Counting successes would penalise the account's real owner, and would
    let an attacker throttle someone by logging in wrongly at their address."""
    email = _email()
    anon_client.post("/auth/register", json={"email": email, "password": PASSWORD})

    for _ in range(settings.auth_email_limit + 2):
        response = anon_client.post(
            "/auth/login", data={"username": email, "password": PASSWORD}
        )

    assert response.status_code == 200


def test_one_users_authenticated_quota_does_not_affect_another(
    memory_limiter, client, other_client, child
):
    """Per-user keying, end to end."""
    for _ in range(settings.authenticated_limit + 5):
        client.get("/quotes")

    assert other_client.get("/quotes").status_code == 200
