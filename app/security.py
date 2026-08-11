"""Password hashing.

Everything here exists to answer one question: when an attacker walks off with
a dump of the users table, how long do the passwords hold?
"""

import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.config import settings

# bcrypt operates on at most 72 bytes and, as of bcrypt 4.x, raises ValueError
# rather than silently truncating. Silent truncation would be worse: a user
# with a 100-character passphrase would find that only the first 72 bytes ever
# mattered, and would never be told.
#
# Bytes, not characters. "e" is one byte but "é" is two in UTF-8 and an emoji
# is four, so a 30-character password can exceed the limit. Validation at the
# schema layer counts bytes for this reason.
MAX_PASSWORD_BYTES = 72


def hash_password(plain: str) -> str:
    """Hash a password for storage.

    Why bcrypt instead of SHA-256, which is also "a hash"?

    Because SHA-256 is built to be fast, and fast is the opposite of what we
    want. Measured on this machine: SHA-256 takes 0.00075 ms per hash, bcrypt
    takes 228 ms. bcrypt is roughly 305,000 times slower, on purpose.

    That number is the entire security argument. Consider the attack that
    actually happens: someone dumps the users table and takes it offline,
    where no login rate limit can touch them. They now guess passwords against
    the stolen hashes as fast as their hardware allows.

      - With SHA-256, commodity GPUs manage billions of guesses per second.
        Every password in any leaked wordlist falls essentially instantly.
      - With bcrypt at 12 rounds, the same hardware manages thousands per
        second. A weak password still falls, but the campaign against everyone
        else becomes months of compute instead of an afternoon.

    So "deliberately slow" buys time -- time for the breach to be detected and
    for users to be forced to rotate. It does not make passwords unbreakable;
    it changes the economics from trivial to expensive.

    The cost factor (12 rounds here, bcrypt's default) is a tuning knob: each
    +1 doubles the work. It can be raised as hardware improves, which is why
    the cost is stored inside each hash -- see below.
    """
    if len(plain.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise ValueError(f"password exceeds {MAX_PASSWORD_BYTES} bytes")

    # gensalt() generates a fresh random salt every call, and hashpw embeds it
    # in the returned string. We never store or manage the salt ourselves.
    #
    # A salt is random data mixed into the password before hashing, and its
    # job is to make every stored hash unique even when two users pick the
    # same password. Without it, identical passwords produce identical hashes,
    # which leaks who shares a password and -- far worse -- lets an attacker
    # precompute one giant table of hash -> password (a rainbow table) and
    # crack the whole database with lookups instead of computation.
    #
    # A salt does not need to be secret. It needs to be unique. It is stored
    # in plain sight right next to the hash and still works, because its only
    # job is to force the attacker to redo the expensive work separately for
    # every single row.
    #
    # The output looks like:
    #     $2b$12$XbMK/Dymt1j68J..IkL9W.K.R16hMyBPt9WTnk0ZeHo3oHEEsqKL2
    #      |   |  |                     |
    #      |   |  +- 22-char salt       +- the actual hash
    #      |   +---- cost: 12 rounds
    #      +-------- algorithm: bcrypt 2b
    #
    # That self-describing format is why raising the cost factor later is
    # painless: old hashes still carry the cost they were made with, so they
    # keep verifying, and you re-hash on next successful login.
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Check a password against a stored hash. Never raises."""
    try:
        # checkpw reads the cost and salt back out of `hashed`, re-hashes
        # `plain` with them, and compares. The comparison is constant-time:
        # it always examines every byte rather than returning early on the
        # first mismatch. An early return would leak, through response timing,
        # how many leading bytes were correct -- enough to recover a hash one
        # byte at a time.
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        # Two real cases land here, and both must read as "wrong password"
        # rather than crashing into a 500:
        #
        #   1. `plain` is over 72 bytes. Someone posting a 5 KB password to
        #      /login should get 401, not a stack trace.
        #   2. `hashed` is not a valid bcrypt string, which raises
        #      "Invalid salt". This is the state of any account we backfilled
        #      with an unusable credential, plus any row corrupted by a bad
        #      migration.
        #
        # Failing closed is the point: an unreadable hash must never be
        # mistaken for a match.
        return False


def create_access_token(user_id: uuid.UUID) -> str:
    """Mint a signed access token identifying one user.

    A JWT is three base64url-encoded segments joined by dots:

        eyJhbGciOiJIUzI1NiIs...  .  eyJzdWIiOiI3M2NiMDYy...  .  4fJ8kQ2mNp...
        └──── header ─────────┘     └──── payload ───────┘     └ signature ┘

    The header names the algorithm. The payload holds the claims. The
    signature is HMAC-SHA256 over the first two segments using our secret.

    The single most misunderstood fact about JWTs: **the payload is encoded,
    not encrypted.** base64url is not a cipher -- it has no key, and anyone
    holding the token can decode the payload with one line of Python or by
    pasting it into jwt.io. The signature does not hide the contents; it only
    proves they have not been altered since we signed them.

    Two consequences follow directly, and they are the whole reason this
    docstring exists:

      1. Never put a secret in the payload. No passwords, no password hashes,
         no API keys, no private personal data. Treat every claim as public.

      2. Do put whatever the server needs to avoid a database round-trip --
         that statelessness is the reason to use a JWT at all. But every claim
         is a snapshot frozen at signing time. Embedding a role or permission
         means a user demoted a minute ago keeps the old privileges until the
         token expires, because nothing re-reads the database.

    This payload therefore carries the bare minimum: which user, and until
    when. The auth dependency looks the user up fresh on every request, so a
    deleted or changed account takes effect immediately. That costs one
    indexed primary-key lookup, which is a good trade for not serving stale
    authorisation.
    """
    now = datetime.now(UTC)

    payload = {
        # "sub" (subject) is a registered claim from RFC 7519 -- the standard
        # slot for "who this token is about". Using the registered name rather
        # than a custom "user_id" means any JWT library or debugger already
        # knows how to read it.
        #
        # Stringified because the JWT spec requires sub to be a string. PyJWT
        # will happily encode a UUID object into JSON-incompatible output or
        # reject it; converting here keeps the token spec-compliant and makes
        # the round-trip through uuid.UUID() on the way back explicit.
        "sub": str(user_id),
        # "exp" is enforced by PyJWT on decode automatically -- an expired
        # token raises ExpiredSignatureError rather than quietly validating.
        # Expiry is checked against the signature, so a client cannot extend
        # its own token without invalidating it.
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
        # "iat" (issued at) is not needed to verify anything here. It is
        # recorded because it is what lets you answer "when was this minted?"
        # during an incident, and because a future revocation scheme can use
        # it to reject every token issued before a password change.
        "iat": now,
    }

    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> uuid.UUID:
    """Verify a token's signature and expiry, and return the user id it names.

    Raises jwt.InvalidTokenError (or a subclass) for anything wrong: bad
    signature, expired, malformed, missing or unusable `sub`. Callers turn
    that into a 401.

    The `algorithms` argument below is the single most important line here,
    and passing it explicitly is not boilerplate.

    A JWT's header declares which algorithm signed it. The catastrophic
    implementation trusts that declaration and verifies using whatever the
    token asks for. Two attacks follow immediately:

      1. alg: none. The spec defines an "unsecured" mode with an empty
         signature. An attacker strips the signature, sets alg to "none", and
         edits the payload to claim any user they like. A library that honours
         the header accepts it, because the token truthfully declares it is
         unsigned.

      2. RS256 -> HS256 confusion. On a server using asymmetric keys, the
         public key is, by design, public. An attacker changes the header to
         HS256 and signs the forged token with that public key as if it were
         an HMAC secret. A trusting verifier reaches for "the key" -- the
         public one -- and the signature checks out.

    Passing an explicit allowlist closes both. We decide what is acceptable
    before looking at the token; the token gets no say. PyJWT makes the
    argument mandatory for exactly this reason, which is a good API choosing
    to be slightly annoying instead of quietly unsafe.
    """
    payload = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],  # allowlist, never the header
    )

    # `exp` was already enforced by jwt.decode -- an expired token raised
    # ExpiredSignatureError before reaching here. Nothing to check manually.
    subject = payload.get("sub")
    if subject is None:
        # A validly signed token with no subject should not exist, since only
        # create_access_token above mints them. If one turns up, something is
        # badly wrong; refuse it rather than guessing.
        raise jwt.InvalidTokenError("token has no subject")

    try:
        return uuid.UUID(subject)
    except (ValueError, AttributeError, TypeError) as exc:
        # Converted rather than allowed to escape. A `sub` that is not a UUID
        # would otherwise raise ValueError out of the dependency and surface
        # as a 500 -- an unhandled crash triggered by attacker-controlled
        # input, and a signal that the input was interesting.
        raise jwt.InvalidTokenError("token subject is not a valid user id") from exc
