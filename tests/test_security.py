"""Unit tests for hashing and token primitives.

These touch no database and no HTTP layer. They exist because the properties
being asserted -- that hashing is salted, that verification fails closed, that
decoding rejects forgeries -- are the ones whose absence is silent. A broken
salt still lets everyone log in; a decoder that accepts alg:none still serves
every valid request. Nothing fails visibly until it is exploited.
"""

import base64
import datetime as dt
import json
import uuid

import jwt
import pytest

from app.config import settings
from app.security import (
    MAX_PASSWORD_BYTES,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hashing_the_same_password_twice_gives_different_hashes():
    """The salt, observed directly.

    If this ever fails, one precomputed rainbow table cracks the whole users
    table at once instead of one row at a time.
    """
    assert hash_password("hunter2") != hash_password("hunter2")


def test_both_hashes_of_the_same_password_still_verify():
    for _ in range(2):
        assert verify_password("hunter2", hash_password("hunter2"))


def test_hash_is_not_the_password():
    assert "hunter2" not in hash_password("hunter2")


def test_hash_carries_its_algorithm_and_cost():
    """The $2b$12$ prefix is what lets the cost be raised later without
    invalidating existing hashes."""
    assert hash_password("hunter2").startswith("$2b$")


def test_verify_rejects_the_wrong_password():
    assert not verify_password("wrong", hash_password("hunter2"))


def test_verify_returns_false_for_a_malformed_hash():
    """bcrypt raises ValueError("Invalid salt") here. Returning False rather
    than propagating keeps a corrupted row -- or an account backfilled with an
    unusable credential -- from turning a login attempt into a 500."""
    assert not verify_password("anything", "not-a-bcrypt-hash")
    assert not verify_password("anything", "")


def test_verify_returns_false_for_an_over_long_password():
    """Fails closed rather than raising, so a 5 KB password is a 401."""
    assert not verify_password("a" * 500, hash_password("hunter2"))


def test_hash_rejects_a_password_over_the_bcrypt_limit():
    with pytest.raises(ValueError):
        hash_password("a" * (MAX_PASSWORD_BYTES + 1))


def test_the_limit_is_bytes_not_characters():
    """30 accented characters are 60 bytes in UTF-8 and fit; 40 are 80 and do
    not. A character-based check would let the second through to explode
    inside bcrypt."""
    assert len(("é" * 30).encode("utf-8")) <= MAX_PASSWORD_BYTES
    hash_password("é" * 30)

    assert len(("é" * 40).encode("utf-8")) > MAX_PASSWORD_BYTES
    with pytest.raises(ValueError):
        hash_password("é" * 40)


# --- tokens ---------------------------------------------------------------


def test_token_round_trips_to_the_same_user_id():
    user_id = uuid.uuid4()
    assert decode_access_token(create_access_token(user_id)) == user_id


def test_token_payload_is_readable_without_the_secret():
    """Not a bug -- the defining property of a JWT, asserted so nobody later
    'improves' this by putting something sensitive in the payload.

    base64url is an encoding, not a cipher. The signature proves the claims
    were not altered; it does nothing to hide them.
    """
    payload_b64 = create_access_token(uuid.uuid4()).split(".")[1]
    payload_b64 += "=" * (-len(payload_b64) % 4)
    claims = json.loads(base64.urlsafe_b64decode(payload_b64))

    assert set(claims) == {"sub", "exp", "iat"}


def test_token_carries_nothing_but_subject_and_timing():
    """Guards against claim creep. Anything added to the payload is public,
    and is frozen at signing time -- an embedded role survives its own
    revocation until the token expires."""
    payload_b64 = create_access_token(uuid.uuid4()).split(".")[1]
    payload_b64 += "=" * (-len(payload_b64) % 4)
    claims = json.loads(base64.urlsafe_b64decode(payload_b64))

    assert "email" not in claims
    assert "password" not in claims
    assert "password_hash" not in claims
    assert "role" not in claims


def test_expired_token_is_rejected():
    now = dt.datetime.now(dt.UTC)
    expired = jwt.encode(
        {"sub": str(uuid.uuid4()), "exp": now - dt.timedelta(seconds=1), "iat": now},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(expired)


def test_token_signed_with_another_secret_is_rejected():
    forged = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "exp": dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
        },
        "a-different-secret-at-least-32-chars-long",
        algorithm="HS256",
    )
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(forged)


def test_alg_none_forgery_is_rejected():
    """The attack the explicit algorithms allowlist exists to stop.

    The JWT spec defines an "unsecured" mode with an empty signature. An
    attacker strips the signature, sets alg to "none", and writes whatever
    subject they like. A verifier that trusts the token's own header accepts
    it, because the token honestly declares itself unsigned.

    Hand-built here: no library will produce this for us, which is rather the
    point -- the forgery is trivial to construct and trivial to accept.
    """

    def b64(d: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()

    victim = uuid.uuid4()
    exp = int((dt.datetime.now(dt.UTC) + dt.timedelta(days=365)).timestamp())
    forged = (
        b64({"alg": "none", "typ": "JWT"})
        + "."
        + b64({"sub": str(victim), "exp": exp})
        + "."
    )

    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(forged)


def test_token_without_a_subject_is_rejected():
    valid_signature_no_sub = jwt.encode(
        {"exp": dt.datetime.now(dt.UTC) + dt.timedelta(hours=1)},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(valid_signature_no_sub)


def test_token_with_a_non_uuid_subject_is_rejected():
    """Must raise InvalidTokenError, not ValueError. The difference is a 401
    versus a 500 -- and a 500 on attacker-controlled input both crashes and
    signals that the input was interesting."""
    bad_sub = jwt.encode(
        {
            "sub": "definitely-not-a-uuid",
            "exp": dt.datetime.now(dt.UTC) + dt.timedelta(hours=1),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(bad_sub)


def test_garbage_is_rejected():
    for junk in ["", "not-a-token", "a.b.c", "...."]:
        with pytest.raises(jwt.InvalidTokenError):
            decode_access_token(junk)
