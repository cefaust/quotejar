"""Liveness and readiness probes.

The load-bearing test here is
test_liveness_still_passes_when_the_database_is_down. It looks trivial and it
encodes the whole reason these are two endpoints: if liveness ever starts
depending on the database, a database blip fails liveness on every instance at
once and the orchestrator restarts all of them, converting a recoverable
outage into a crash-loop.

That regression is a one-line change -- adding a `db` dependency to liveness --
and it would look like an improvement in review. This test is what stops it.
"""

from sqlalchemy.exc import OperationalError

from app.db import get_db
from app.main import app


class _BrokenSession:
    """A session whose every query fails, standing in for an unreachable
    database. Simulated rather than actually stopping Postgres, so the test
    runs in milliseconds and does not disturb the other tests' database."""

    def execute(self, *_args, **_kwargs):
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    def close(self):
        pass


def _with_broken_db():
    yield _BrokenSession()


# --- liveness -------------------------------------------------------------


def test_liveness_returns_alive(anon_client):
    r = anon_client.get("/health/live")

    assert r.status_code == 200
    assert r.json() == {"status": "alive"}


def test_liveness_still_passes_when_the_database_is_down(anon_client):
    """The point of splitting the probes.

    A failing liveness check means "restart me", and restarting the
    application does not fix a database that is down -- it turns a
    thirty-second blip into a crash-loop across every instance. Liveness must
    therefore depend on nothing but the process.
    """
    app.dependency_overrides[get_db] = _with_broken_db
    try:
        r = anon_client.get("/health/live")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert r.status_code == 200


def test_liveness_needs_no_authentication(anon_client):
    """A probe cannot hold credentials, and a 401 reads as an unhealthy
    instance."""
    assert anon_client.get("/health/live").status_code == 200


# --- readiness ------------------------------------------------------------


def test_readiness_returns_ready_when_the_database_is_reachable(anon_client):
    r = anon_client.get("/health/ready")

    assert r.status_code == 200
    assert r.json() == {"status": "ready"}


def test_readiness_returns_503_when_the_database_is_unreachable(anon_client):
    """503, not 500. 500 means "this request hit a bug"; 503 means "this
    instance cannot serve right now" -- which is what a load balancer knows
    how to act on."""
    app.dependency_overrides[get_db] = _with_broken_db
    try:
        r = anon_client.get("/health/ready")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert r.status_code == 503
    assert r.json()["status"] == "not ready"


def test_readiness_failure_does_not_leak_connection_details(anon_client):
    """Driver errors can carry the connection string, and readiness endpoints
    are unauthenticated and routinely scraped into logs and dashboards. Only
    the exception type is reported."""
    app.dependency_overrides[get_db] = _with_broken_db
    try:
        body = anon_client.get("/health/ready").text
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert "connection refused" not in body
    assert "postgresql" not in body.lower()
    assert "password" not in body.lower()


def test_readiness_needs_no_authentication(anon_client):
    assert anon_client.get("/health/ready").status_code == 200


# --- the legacy alias -----------------------------------------------------


def test_legacy_health_still_works(anon_client):
    """QJ-1 and QJ-2 documented /health; anything already pointed at it keeps
    working."""
    r = anon_client.get("/health")

    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_legacy_health_has_liveness_semantics(anon_client):
    """It never checked the database, so callers depend on liveness semantics
    whether they knew it or not. Silently upgrading it to readiness would
    change its meaning for every existing caller."""
    app.dependency_overrides[get_db] = _with_broken_db
    try:
        r = anon_client.get("/health")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert r.status_code == 200
