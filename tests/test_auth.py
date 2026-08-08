"""Registration, login, and the token dependency, at the HTTP layer."""

import datetime as dt
import uuid

import jwt
from sqlalchemy import select

from app.config import settings
from app.models import User
from app.security import create_access_token

REGISTER = "/auth/register"
LOGIN = "/auth/login"
ME = "/auth/me"

GOOD_PASSWORD = "correct-horse-battery"


def _email() -> str:
    return f"{uuid.uuid4()}@example.com"


# --- registration ---------------------------------------------------------


def test_register_creates_a_user(anon_client):
    email = _email()
    r = anon_client.post(REGISTER, json={"email": email, "password": GOOD_PASSWORD})

    assert r.status_code == 201
    assert r.json()["email"] == email
    assert uuid.UUID(r.json()["id"])


def test_register_never_returns_the_password_or_its_hash(anon_client):
    """UserRead is an allowlist, so this holds even though the handler returns
    the whole ORM object. Asserted anyway: adding password_hash to the schema
    would be a one-line mistake with no other visible symptom."""
    r = anon_client.post(REGISTER, json={"email": _email(), "password": GOOD_PASSWORD})

    assert "password" not in r.text
    assert "password_hash" not in r.json()
    assert GOOD_PASSWORD not in r.text


def test_register_stores_a_hash_rather_than_the_password(anon_client, db):
    email = _email()
    anon_client.post(REGISTER, json={"email": email, "password": GOOD_PASSWORD})

    stored = db.scalar(select(User).where(User.email == email))
    assert stored.password_hash != GOOD_PASSWORD
    assert stored.password_hash.startswith("$2b$")


def test_register_leaves_display_name_empty(anon_client):
    """Signup takes email and password only; nothing is invented for the
    display name."""
    r = anon_client.post(REGISTER, json={"email": _email(), "password": GOOD_PASSWORD})

    assert r.json()["display_name"] is None


def test_register_rejects_a_duplicate_email(anon_client):
    email = _email()
    anon_client.post(REGISTER, json={"email": email, "password": GOOD_PASSWORD})

    r = anon_client.post(REGISTER, json={"email": email, "password": GOOD_PASSWORD})
    assert r.status_code == 409


def test_register_rejects_a_malformed_email(anon_client):
    r = anon_client.post(REGISTER, json={"email": "not-an-email", "password": GOOD_PASSWORD})
    assert r.status_code == 422


def test_register_rejects_a_short_password(anon_client):
    r = anon_client.post(REGISTER, json={"email": _email(), "password": "short"})
    assert r.status_code == 422


def test_register_rejects_a_password_over_72_bytes_with_422_not_500(anon_client):
    """The byte-versus-character trap. 30 plain characters plus 30 accented
    ones is 60 characters but 90 bytes, so a max_length check would pass it
    through to bcrypt, which raises -- surfacing as a 500."""
    too_long = "e" * 30 + "é" * 30
    assert len(too_long) < 72 < len(too_long.encode("utf-8"))

    r = anon_client.post(REGISTER, json={"email": _email(), "password": too_long})
    assert r.status_code == 422


# --- login ----------------------------------------------------------------


def test_login_returns_a_bearer_token(anon_client):
    email = _email()
    anon_client.post(REGISTER, json={"email": email, "password": GOOD_PASSWORD})

    r = anon_client.post(LOGIN, data={"username": email, "password": GOOD_PASSWORD})

    assert r.status_code == 200
    assert r.json()["token_type"] == "bearer"
    assert r.json()["access_token"]


def test_login_rejects_a_wrong_password(anon_client):
    email = _email()
    anon_client.post(REGISTER, json={"email": email, "password": GOOD_PASSWORD})

    r = anon_client.post(LOGIN, data={"username": email, "password": "wrong-password"})
    assert r.status_code == 401


def test_login_rejects_an_unknown_email(anon_client):
    r = anon_client.post(LOGIN, data={"username": _email(), "password": GOOD_PASSWORD})
    assert r.status_code == 401


def test_login_failures_are_indistinguishable(anon_client):
    """"No such user" and "wrong password" must be one answer.

    Distinguishing them hands an attacker a free oracle for which addresses
    are registered -- the list that gets fed into credential stuffing
    elsewhere. The timing defence in the handler is worthless if the body
    gives it away instead.
    """
    email = _email()
    anon_client.post(REGISTER, json={"email": email, "password": GOOD_PASSWORD})

    wrong_password = anon_client.post(
        LOGIN, data={"username": email, "password": "wrong-password"}
    )
    no_such_user = anon_client.post(
        LOGIN, data={"username": _email(), "password": GOOD_PASSWORD}
    )

    assert wrong_password.status_code == no_such_user.status_code == 401
    assert wrong_password.json() == no_such_user.json()


def test_login_requires_form_encoding_not_json(anon_client):
    """Documents the one place the API breaks JSON consistency. It is the
    price of OAuth2PasswordRequestForm and Swagger's Authorize button."""
    email = _email()
    anon_client.post(REGISTER, json={"email": email, "password": GOOD_PASSWORD})

    r = anon_client.post(LOGIN, json={"username": email, "password": GOOD_PASSWORD})
    assert r.status_code == 422


def test_a_registered_user_can_log_in_and_use_the_token(anon_client):
    """The whole flow, end to end, as a client would actually do it."""
    email = _email()
    anon_client.post(REGISTER, json={"email": email, "password": GOOD_PASSWORD})
    token = anon_client.post(
        LOGIN, data={"username": email, "password": GOOD_PASSWORD}
    ).json()["access_token"]

    r = anon_client.get(ME, headers={"Authorization": f"Bearer {token}"})

    assert r.status_code == 200
    assert r.json()["email"] == email


# --- the dependency -------------------------------------------------------


def test_me_returns_the_authenticated_user(client, user):
    r = client.get(ME)

    assert r.status_code == 200
    assert r.json()["id"] == str(user.id)


def test_me_requires_a_token(anon_client):
    assert anon_client.get(ME).status_code == 401


def test_me_rejects_a_garbage_token(anon_client):
    r = anon_client.get(ME, headers={"Authorization": "Bearer not-a-token"})
    assert r.status_code == 401


def test_me_rejects_an_expired_token(anon_client, user):
    now = dt.datetime.now(dt.timezone.utc)
    expired = jwt.encode(
        {"sub": str(user.id), "exp": now - dt.timedelta(hours=1), "iat": now},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    r = anon_client.get(ME, headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401


def test_me_rejects_a_token_signed_with_another_secret(anon_client, user):
    forged = jwt.encode(
        {"sub": str(user.id), "exp": dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)},
        "a-different-secret-at-least-32-chars-long",
        algorithm="HS256",
    )

    r = anon_client.get(ME, headers={"Authorization": f"Bearer {forged}"})
    assert r.status_code == 401


def test_me_rejects_a_token_for_a_deleted_user(anon_client, db, user):
    """Why the dependency re-reads the database instead of trusting claims.

    The token is untampered and unexpired -- we signed it ourselves. If auth
    were served from claims alone, this deleted account would keep working
    for the rest of the token's 30-minute life.
    """
    token = create_access_token(user.id)
    db.delete(user)
    db.flush()

    r = anon_client.get(ME, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_all_token_failures_return_the_same_body(anon_client, user):
    """Distinguishing "expired" from "bad signature" tells an attacker probing
    with forgeries that the signing was right and only the timestamp was
    stale -- precise feedback on how close they are."""
    now = dt.datetime.now(dt.timezone.utc)
    expired = jwt.encode(
        {"sub": str(user.id), "exp": now - dt.timedelta(hours=1)},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    wrong_secret = jwt.encode(
        {"sub": str(user.id), "exp": now + dt.timedelta(hours=1)},
        "a-different-secret-at-least-32-chars-long",
        algorithm="HS256",
    )

    bodies = {
        anon_client.get(ME, headers={"Authorization": f"Bearer {t}"}).json()["detail"]
        for t in (expired, wrong_secret, "garbage")
    }
    assert len(bodies) == 1
