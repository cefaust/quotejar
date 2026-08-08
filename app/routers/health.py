"""Liveness and readiness probes.

QJ-2 flagged that `/health` returned `{"status": "ok"}` unconditionally, so an
instance whose database connection was dead still reported healthy to anything
polling it. This collects that gap.

The two probes answer genuinely different questions, and conflating them is
one of the more expensive mistakes in container operations:

  **Liveness** — "is this process wedged?" A failure means *restart me*. It
  must depend on nothing but the process itself.

  **Readiness** — "can I serve a request right now?" A failure means *stop
  routing traffic to me*, but leave me running.

The critical rule, and the reason this file is two endpoints rather than one:

    Liveness must NOT check the database.

If it did, a database blip would fail liveness on *every* instance
simultaneously, and the orchestrator would respond by restarting all of them.
Restarting your application does not fix a database that is down. What it does
is turn a recoverable thirty-second outage into a crash-loop: instances die,
restart, fail their probe again during startup, get killed again, and the
platform eventually backs off into a state that needs human intervention. You
have converted a dependency blip into a self-inflicted outage, and you did it
by being conscientious about health checks.

Readiness is where the database belongs. When it fails, instances stay alive
and keep their place; the load balancer simply stops sending them work. The
moment the database recovers, readiness passes again and traffic resumes with
nothing restarted.

App Runner only consumes one health check path, and it behaves as readiness
(it removes failing instances from rotation). It is pointed at /health/ready.
The liveness endpoint still earns its place: it is what you curl to
distinguish "the process is gone" from "the process is up but the database is
unreachable" — the first question you ask at 3am, and one a combined probe
cannot answer.
"""

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db import get_db

router = APIRouter(tags=["health"])


@router.get("/health/live")
def liveness() -> dict[str, str]:
    """Is the process running and able to answer?

    Deliberately checks nothing. If this handler executes at all, the answer
    is yes: the process is up, the event loop is turning, and the HTTP stack
    is serving. Any dependency added here would let an external outage trigger
    restarts, which is the failure described in the module docstring.

    This is not laziness. An empty liveness check is the correct liveness
    check for a stateless web process.
    """
    return {"status": "alive"}


@router.get("/health/ready")
def readiness(response: Response, db: Session = Depends(get_db)) -> dict[str, str]:
    """Can this instance actually serve a request?

    Every endpoint except the auth-free ones needs the database, so database
    reachability is what readiness means here.

    `SELECT 1` is deliberately the cheapest query that still proves something
    real. It exercises the whole path -- connection pool, socket, credentials,
    the server being awake enough to parse and answer -- without touching a
    table, taking a lock, or being affected by how much data exists. A probe
    that runs a real query would eventually become the slowest thing hitting
    the database, and a probe that gets slower under load will fail exactly
    when you least want instances pulled from rotation.

    `pool_pre_ping` on the engine means the pool validates a connection before
    handing it over, so a connection killed by an RDS failover or an idle
    timeout is discarded and replaced rather than surfacing here as a false
    negative.

    Returns 503 rather than raising, so the body still explains what failed.
    """
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        # 503 Service Unavailable, not 500. 500 says "this request hit a bug";
        # 503 says "this instance cannot serve right now, try another or try
        # later" -- which is exactly true, and is what load balancers and
        # orchestrators are built to react to.
        #
        # The exception type is included but not the message. Driver errors
        # can carry the connection string, and readiness endpoints are
        # routinely unauthenticated and scraped into logs and dashboards.
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "not ready", "reason": type(exc).__name__}

    return {"status": "ready"}
