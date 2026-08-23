"""Registration and token issuance.

A note on what this is and is not, because the naming invites a claim you do
not want to make in an interview.

The login endpoint accepts an OAuth2 *password grant* request shape, via
FastAPI's OAuth2PasswordRequestForm. That is where the borrowing stops. There
is no third-party authorisation server here, no client registration, no
consent screen, no delegation -- none of the machinery that makes OAuth2
OAuth2. The password grant is in fact deprecated in OAuth 2.1, whose authors
recommend against it for new applications, precisely because handing your
password directly to the application defeats the delegation OAuth exists to
provide.

What we get in exchange is FastAPI's tooling: OAuth2PasswordBearer, the
Authorize button in Swagger, and the documented dependency-injection path.

So: "I used FastAPI's OAuth2PasswordRequestForm for the token endpoint," not
"I implemented OAuth2."
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.dependencies import (
    AuthIpRateLimit,
    CurrentUser,
    DbSession,
    _too_many_requests,
    limiter,
)
from app.models import User
from app.schemas import Token, UserCreate, UserRead
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

# A real bcrypt hash of a value nobody knows, used only to burn time.
#
# See the comment in login() -- this exists so that a login attempt for an
# address that does not exist costs the same as one for an address that does.
_DUMMY_HASH = hash_password("a-password-that-is-never-anyone's")


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[AuthIpRateLimit],
)
def register(payload: UserCreate, db: DbSession) -> User:
    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
    )
    db.add(user)

    # Let the database decide whether the email is taken, rather than running
    # a SELECT first and inserting if it comes back empty.
    #
    # That check-then-insert pattern has a race: two requests for the same
    # address can both run the SELECT, both see nothing, and both proceed. The
    # window is small but it is real, and under concurrent signups it is
    # exactly when you would least like to find out. The UNIQUE constraint on
    # users.email is enforced by Postgres and cannot be raced, so it is the
    # only honest source of truth. We attempt the insert and translate the
    # failure.
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # 409 Conflict, and it does disclose that this address is registered.
        #
        # That is a genuine user-enumeration leak, and worth naming rather
        # than pretending otherwise. Closing it means never confirming or
        # denying at signup -- accepting every registration, then emailing
        # either a welcome or a "someone tried to register your address"
        # notice, so the browser learns nothing. That requires the email
        # delivery and verification flow that QJ-2 puts out of scope.
        #
        # Login, below, does not have this excuse and does not leak.
        #
        # `from None` suppresses the exception chain deliberately, and is not
        # merely appeasing B904. The chained IntegrityError carries the raw
        # Postgres message, which names the constraint, the table, and the
        # conflicting value. That would reach the logs on every duplicate
        # signup and, if error detail were ever surfaced to clients, the
        # response. The 409 already says everything a caller should learn.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with that email already exists",
        ) from None

    db.refresh(user)
    return user


@router.post("/login", response_model=Token, dependencies=[AuthIpRateLimit])
def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: DbSession,
) -> Token:
    """Exchange credentials for an access token.

    This endpoint takes application/x-www-form-urlencoded, not JSON, and the
    email arrives in a field called `username`. Both are inherited from the
    OAuth2 password-grant shape and neither can be renamed -- FastAPI's
    Swagger integration and OAuth2PasswordBearer both look for those exact
    names. It is the one endpoint in this API that breaks JSON consistency,
    and that inconsistency is the price of the tooling.
    """
    # The per-email limit, checked before any work happens.
    #
    # A second axis from the per-IP limit applied by the decorator, because the
    # two protect different things and each is blind where the other sees. The
    # IP limit protects the service from resource exhaustion; this protects one
    # account from credential stuffing. An attacker with a botnet defeats the
    # IP limit while every attempt still lands on one address, and conversely a
    # shared NAT puts thousands of innocent users behind a single IP.
    #
    # Lowercased so Alice@example.com and alice@example.com share a bucket
    # rather than handing an attacker a fresh allowance per capitalisation.
    email_key = form_data.username.lower()
    if settings.rate_limit_enabled:
        decision = limiter.peek(
            "auth-email",
            email_key,
            settings.auth_email_limit,
            settings.auth_email_window_seconds,
        )
        if not decision.allowed:
            raise _too_many_requests(decision)

    user = db.scalar(select(User).where(User.email == form_data.username))

    # Verify a password on every path, even when no such user exists.
    #
    # The obvious implementation returns 401 immediately when the lookup finds
    # nothing. That is a timing oracle: the "no such user" path skips bcrypt
    # and answers in under a millisecond, while the "user exists, wrong
    # password" path spends ~230 ms hashing. An attacker with a list of
    # addresses does not need the response body -- a stopwatch tells them
    # which ones are registered, and that list is what gets fed into credential
    # stuffing against other sites.
    #
    # Hashing against a throwaway hash equalises the two paths. It is wasted
    # CPU by design.
    if user is None:
        verify_password(form_data.password, _DUMMY_HASH)
        _record_failure(email_key)
        raise _invalid_credentials()

    if not verify_password(form_data.password, user.password_hash):
        _record_failure(email_key)
        raise _invalid_credentials()

    return Token(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserRead)
def read_current_user(user: CurrentUser) -> User:
    """Return the authenticated user.

    Small, but it earns its place: it is the one route whose entire behaviour
    is "did the token resolve to somebody", which makes it the natural target
    for testing every token rejection path without dragging quotes or children
    into it. Clients also need it to confirm a stored token is still good
    without attempting a write.
    """
    return user


def _record_failure(email_key: str) -> None:
    """Count one failed attempt against the address that was tried.

    Failures only. A user who types their password correctly has not attacked
    anything, and counting successes would do two harmful things: penalise the
    account's legitimate owner for using it, and hand an attacker a way to lock
    someone out by deliberately failing at their address. That second one is
    why account lockout is out of scope -- see README.md.

    Recorded for unknown addresses too. Skipping it there would leak which
    addresses exist: an attacker could tell registered from unregistered by
    whether attempts started being throttled.
    """
    if settings.rate_limit_enabled:
        limiter.record("auth-email", email_key, settings.auth_email_window_seconds)


def _invalid_credentials() -> HTTPException:
    """One error for both failure modes.

    "No such user" and "wrong password" deliberately produce an identical
    status, message, and header. Distinguishing them is friendlier to a
    forgetful user and strictly more useful to an attacker, who gets a free
    oracle for which addresses are registered. The vaguer message is the
    correct trade, and it is why the timing has to match too -- a distinct
    message closed through the front door means nothing if the response time
    still announces the answer.

    401 with WWW-Authenticate is what the HTTP spec asks for: the header tells
    the client which scheme to authenticate with, and Swagger reads it.
    """
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Incorrect email or password",
        headers={"WWW-Authenticate": "Bearer"},
    )
