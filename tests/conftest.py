import uuid
from collections.abc import Generator

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.db import Base, get_db
from app.main import app
from app.models import Child, User
from app.security import hash_password

TEST_URL = settings.test_database_url


@pytest.fixture(scope="session")
def engine():
    if TEST_URL is None:
        pytest.fail("TEST_DATABASE_URL is not set")

    engine = create_engine(TEST_URL)

    # Start from a known-empty schema, then let Alembic build it.
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("script_location", "alembic")
    alembic_cfg.set_main_option("sqlalchemy.url", TEST_URL)
    command.upgrade(alembic_cfg, "head")

    yield engine
    engine.dispose()


@pytest.fixture
def db(engine) -> Generator[Session, None, None]:
    """Each test runs inside a transaction that is rolled back afterwards."""
    connection = engine.connect()
    transaction = connection.begin()
    session = sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# Hashed once at import, then reused by every fixture below.
#
# bcrypt costs ~230 ms per hash by design (see app/security.py). Calling it
# per-test would add roughly a quarter second to each one -- the whole QJ-1
# suite currently runs in 0.3 s, so hashing inline would make the tests over
# ten times slower for no coverage gain. The hashing itself is tested directly
# in the security tests; fixtures just need *a* valid hash.
TEST_PASSWORD = "correct-horse-battery"
TEST_PASSWORD_HASH = hash_password(TEST_PASSWORD)


@pytest.fixture
def child(db) -> Child:
    user = User(
        email=f"{uuid.uuid4()}@example.com",
        display_name="Test Parent",
        password_hash=TEST_PASSWORD_HASH,
    )
    db.add(user)
    db.flush()
    child = Child(user_id=user.id, name="Ada")
    db.add(child)
    db.flush()
    return child
