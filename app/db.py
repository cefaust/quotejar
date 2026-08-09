"""Database engine and session factory.

The engine is created here, at module scope, and that placement is load-bearing
in Lambda. Module-level code runs once per cold start; handler code runs once
per invocation. An engine built inside the handler would open a fresh TCP
connection, negotiate TLS, and authenticate against Postgres on *every single
request* -- tens of milliseconds of pure overhead, and a connection churn rate
the database has to absorb. Built here, warm invocations reuse an established
connection and pay none of it.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

# --- Connection pool sizing -------------------------------------------------
#
# This is sized against the *database*, not the application, and the numbers
# are measured rather than assumed.
#
# Measured on this db.t4g.micro instance:
#
#     max_connections                 79
#     superuser_reserved_connections   3
#     baseline in use                  9   (RDS internals, monitoring)
#     ------------------------------------
#     usable by the application       67
#
# Now the failure this prevents. Every warm Lambda instance holds its own
# pool -- pools are per-process, and each Lambda is a separate process. So
# total connections are (instances) x (pool_size + max_overflow).
#
# SQLAlchemy's defaults are pool_size=5, max_overflow=10, which is 15 per
# instance. With the reserved concurrency of 5 that this deployment sets:
#
#     5 instances x 15 = 75 connections  >  67 usable
#
# The default configuration overshoots the database by itself. That is the
# trap: capping Lambda concurrency at 5 *feels* like it bounds the problem,
# and it does not, because nothing bounds how many connections each instance
# opens. Postgres starts refusing new connections with "remaining connection
# slots are reserved" -- and it refuses everyone, including psql from your
# laptop, so the outage locks you out of the box you need to diagnose it from.
#
# Each Lambda instance processes exactly one event at a time, so it needs
# exactly one connection at a time. One spare absorbs the readiness probe
# overlapping a request.
#
#     5 instances x (1 + 1) = 10 connections  <<  67 usable
#
# Leaving ample headroom for migrations, psql, and anything else run by hand.
#
# The alternative at larger scale is RDS Proxy, which multiplexes many client
# connections onto few database ones. It costs roughly $20/month and solves a
# problem this deployment does not have. Capping concurrency and sizing the
# pool is the same protection for nothing.
engine = create_engine(
    settings.database_url,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    # Essential in Lambda specifically. Between invocations the execution
    # environment is frozen, not stopped -- a pooled connection can sit idle
    # for minutes while RDS, a NAT timeout, or a failover silently drops the
    # other end. Without pre-ping the first query after a freeze fails with a
    # stale-connection error that looks random and is maddening to reproduce.
    # Pre-ping costs one trivial round-trip and turns that into a transparent
    # reconnect.
    pool_pre_ping=True,
    # Recycle before RDS's own idle timeout can act. Belt and braces with
    # pre-ping: pre-ping detects a dead connection, recycle avoids having one.
    pool_recycle=1800,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        # Returns the connection to the pool rather than closing the socket.
        # With pool_size=1 this matters: failing to release would deadlock the
        # next request on an exhausted pool.
        db.close()
