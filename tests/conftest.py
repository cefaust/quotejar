import uuid
from collections.abc import Generator

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from alembic import command
from app.config import settings
from app.db import get_db
from app.dependencies import limiter
from app.main import app
from app.models import Child, User
from app.security import create_access_token, hash_password

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


# Hashed once at import, then reused by every fixture below.
#
# bcrypt costs ~230 ms per hash by design (see app/security.py). Calling it
# per-test would add roughly a quarter second to each one -- the whole QJ-1
# suite currently runs in 0.3 s, so hashing inline would make the tests over
# ten times slower for no coverage gain. The hashing itself is tested directly
# in the security tests; fixtures just need *a* valid hash.
TEST_PASSWORD = "correct-horse-battery"
TEST_PASSWORD_HASH = hash_password(TEST_PASSWORD)


def _make_user(db: Session) -> User:
    user = User(
        email=f"{uuid.uuid4()}@example.com",
        display_name="Test Parent",
        password_hash=TEST_PASSWORD_HASH,
    )
    db.add(user)
    db.flush()
    return user


@pytest.fixture
def user(db) -> User:
    return _make_user(db)


@pytest.fixture
def other_user(db) -> User:
    """A second, unrelated account.

    Exists so cross-user tests can be written as "B does X to A's thing"
    rather than by hand-rolling a second user inside each test. Access-control
    coverage is only meaningful with two real identities in play.
    """
    return _make_user(db)


@pytest.fixture
def anon_client(db) -> Generator[TestClient, None, None]:
    """A client with no credentials, for asserting endpoints reject anonymity."""
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def client(db, user) -> Generator[TestClient, None, None]:
    """A client authenticated as `user`.

    Authenticated by default, deliberately. Every endpoint except register and
    login now requires a token, so an unauthenticated client is the exception
    rather than the norm -- and a fixture that makes the common case the
    default is one people will actually use. Tests that need anonymity ask for
    anon_client explicitly, which also makes those tests self-documenting.

    The token is minted directly rather than by POSTing to /auth/login. Going
    through the endpoint would couple every quotes test to the login handler,
    so a bug there would redden the entire suite instead of just the login
    tests. It also avoids a bcrypt verify per test.
    """
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        c.headers["Authorization"] = f"Bearer {create_access_token(user.id)}"
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def other_client(db, other_user) -> Generator[TestClient, None, None]:
    """A client authenticated as `other_user` -- the attacker in IDOR tests."""
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        c.headers["Authorization"] = f"Bearer {create_access_token(other_user.id)}"
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def child(db, user) -> Child:
    child = Child(user_id=user.id, name="Ada")
    db.add(child)
    db.flush()
    return child


@pytest.fixture
def other_child(db, other_user) -> Child:
    """A child belonging to the *other* account."""
    child = Child(user_id=other_user.id, name="Bo")
    db.add(child)
    db.flush()
    return child


class MemoryStore:
    """Rate-limit counters in a dict. Same contract as DynamoDBStore.

    Lives in conftest rather than the test module because every test needs it,
    not only the rate-limit tests -- see isolated_rate_limiter below.
    """

    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    def increment(self, key: str, window_seconds: int) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    def get(self, key: str) -> int:
        return self.counts.get(key, 0)


@pytest.fixture(autouse=True)
def isolated_rate_limiter():
    """Give every test its own empty rate-limit store.

    Autouse, and not optional. Without it the suite's behaviour depends on
    whether boto3 happens to be installed and whether AWS credentials happen to
    be present: with neither, the limiter fails open and every test passes; with
    both, the tests write to the *production* DynamoDB table and start
    throttling each other. That was not hypothetical -- it produced 35 rows in
    the real table and six failures asserting `429 == 401`.

    Fresh per test as well as isolated, so one test exhausting a limit cannot
    leak into the next and produce failures that depend on execution order.
    """
    original = limiter.store
    limiter.store = MemoryStore()
    yield
    limiter.store = original
