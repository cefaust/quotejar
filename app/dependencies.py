"""The authentication dependency.

Everything an endpoint needs to say "this route requires a logged-in user"
lives here, as a single injectable that yields the User or refuses the request.
"""

from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import User
from app.ratelimit import Decision, DynamoDBStore, RateLimiter
from app.security import decode_access_token

# tokenUrl is documentation, not routing. FastAPI never calls it; it is
# written into the OpenAPI schema so Swagger's Authorize button knows where to
# POST credentials. It must match the real login route -- "auth/login", no
# leading slash, per the OpenAPI convention of paths relative to the server
# root. Get it wrong and everything still works from curl while the Authorize
# button silently posts into the void.
#
# This object is also what puts securitySchemes into the OpenAPI document, so
# adding it is what makes the padlock icons appear on protected routes.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    """Resolve the bearer token to a User, or refuse with 401.

    Why this re-reads the database on every request instead of trusting the
    token's claims.

    A JWT is a snapshot frozen at signing time. Everything in the payload was
    true when the token was minted and is asserted, unverified, for as long as
    the token lives -- up to 30 minutes here. Serving a request purely from
    claims means:

      - a deleted account keeps working until expiry
      - a user whose permissions were revoked keeps the old ones
      - a disabled or banned account is still fully functional

    The lookup costs one primary-key index hit, which is about as cheap as a
    query gets, and buys back the ability to make a change take effect now.
    That is the right trade for authorisation data. The statelessness a JWT
    buys is still real -- we skipped a session table and a session store -- we
    are just not extending it to "and never check whether this user still
    exists."
    """
    try:
        user_id = decode_access_token(token)
    except jwt.InvalidTokenError:
        # One handler for every failure mode -- expired, tampered signature,
        # wrong algorithm, structurally malformed, missing subject.
        #
        # Deliberately not distinguished. "Token expired" versus "signature
        # invalid" tells an attacker probing with forged tokens whether they
        # got the signing right and merely need a fresher timestamp, which is
        # precise feedback on how close they are. A legitimate client does not
        # need the difference either: the response to any of these is the
        # same, log in again.
        #
        # `from None` is load-bearing here rather than lint appeasement. The
        # whole point of this handler is that the failure modes are
        # indistinguishable; chaining the original would put "Signature
        # verification failed" or "Signature has expired" straight into the
        # logs beside the request, reconstructing exactly the distinction the
        # 401 refuses to make.
        raise _unauthenticated() from None

    user = db.get(User, user_id)
    if user is None:
        # Signature was valid, so we minted this token -- but the account is
        # gone. Deleted since issue, or the database was restored from a
        # backup predating it.
        raise _unauthenticated()

    return user


def _unauthenticated() -> HTTPException:
    """401, not 403, and the distinction is worth being precise about.

    401 Unauthorized means "I do not know who you are" -- no credentials, or
    credentials that did not check out. The correct client response is to
    authenticate and retry, which is why the spec requires the
    WWW-Authenticate header naming the scheme to use.

    403 Forbidden means "I know exactly who you are, and the answer is still
    no." Retrying with the same identity is pointless.

    Everything in this module is the first case: the token did not resolve to
    a user, so there is no identity to make a decision about yet. Returning
    403 would tell a client with an expired token that re-authenticating is
    futile, when it is precisely the fix.

    (Note that this is a different question from the one in the quotes router,
    where we deliberately return 404 rather than 403 for another user's
    resource. There the identity is known and valid -- the reasoning there is
    about not confirming that a resource exists.)
    """
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


# Endpoints write `user: CurrentUser` instead of repeating the Depends() call.
# Beyond brevity, it means the auth requirement is a single named thing that
# can be changed in one place.
CurrentUser = Annotated[User, Depends(get_current_user)]

# The same treatment for the database session.
#
# The older FastAPI style is `db: Session = Depends(get_db)` -- a function call
# evaluated once, at import, and used as a default argument. FastAPI handles
# that correctly, but it is genuinely unusual Python: mutable or
# call-evaluated defaults are a well-known footgun, which is why ruff's B008
# flags all eleven occurrences of it in this codebase.
#
# Annotated moves the dependency into the *type* rather than the default, so
# the parameter has no default at all. That silences B008 by removing the
# pattern it warns about, not by suppressing the warning -- which matters,
# because a per-rule ignore would also hide a real accidental call-in-default
# somewhere else later.
#
# It is also what FastAPI's own documentation now recommends, and it composes:
# `Annotated` types can be aliased, reused, and read by type checkers, where a
# default-argument Depends cannot.
DbSession = Annotated[Session, Depends(get_db)]


# --- Rate limiting ---------------------------------------------------------

# Built once, at import. Same reasoning as the SQLAlchemy engine and the
# Secrets Manager fetch: module-level code runs once per cold start, handler
# code runs per invocation. Constructing a boto3 client per request would add
# a service-model load to every call.
limiter = RateLimiter(DynamoDBStore(settings.rate_limit_table))


def client_ip(request: Request) -> str:
    """The caller's address, from the one source that cannot be forged.

    `request.client.host` comes from `requestContext.http.sourceIp`, which AWS
    populates from the actual TCP connection. A caller cannot influence it.

    **X-Forwarded-For is deliberately ignored, and this is the whole point.**
    Most rate-limiting guidance says to prefer it, because most deployments sit
    behind a load balancer that sets it. Nothing sits in front of this Function
    URL, so the header arrives exactly as the client typed it. Verified
    directly: a request carrying `X-Forwarded-For: 1.2.3.4` still reports
    sourceIp as its real address, and the header passes through untouched.
    Keying on it would let an attacker defeat every IP limit by incrementing a
    header, which is worse than having no limit at all -- it would look like
    protection while providing none.

    **What must change if anything is ever put in front.** Adding CloudFront
    (as the WAF option in QJ-6 would have required) makes sourceIp CloudFront's
    address, so every user in the world collapses into a handful of edge IPs
    and the limit becomes global. At that point the correct source is the
    rightmost untrusted entry in X-Forwarded-For, or `CloudFront-Viewer-Address`
    -- but only once the origin is locked down so the Function URL cannot be
    reached directly, because otherwise an attacker skips the proxy and forges
    the header anyway.
    """
    return request.client.host if request.client else "unknown"


def _too_many_requests(decision: Decision) -> HTTPException:
    """429 with enough information for a client to behave well.

    Retry-After alongside the RateLimit-* fields: the former is RFC 9110 and
    almost universally understood, the latter is the newer IETF draft and
    carries the full quota picture. Sending both means any client that
    understands either can back off correctly.
    """
    headers = decision.headers()
    headers["Retry-After"] = str(decision.reset_seconds)
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Too many requests. Please retry later.",
        headers=headers,
    )


def enforce_auth_ip_limit(request: Request) -> None:
    """Per-IP limit for login and register.

    Applied before the handler runs, so a rejected request never reaches
    bcrypt. That ordering is the entire defence: the cost being rationed is
    216 ms of CPU, and a limiter that ran afterwards would ration nothing.
    """
    if not settings.rate_limit_enabled:
        return
    decision = limiter.check(
        "auth-ip",
        client_ip(request),
        settings.auth_ip_limit,
        settings.auth_ip_window_seconds,
    )
    if not decision.allowed:
        raise _too_many_requests(decision)


def enforce_user_limit(user: CurrentUser) -> User:
    """Per-user-ID limit for authenticated endpoints.

    Runs after get_current_user, so the token has already been validated and
    there is a real identity to key on.
    """
    if not settings.rate_limit_enabled:
        return user
    decision = limiter.check(
        "user",
        str(user.id),
        settings.authenticated_limit,
        settings.authenticated_window_seconds,
    )
    if not decision.allowed:
        raise _too_many_requests(decision)
    return user


# Endpoints write `user: RateLimitedUser` instead of `user: CurrentUser` to opt
# into the per-user limit. Keeping them as separate aliases makes the choice
# explicit at each endpoint rather than hidden in middleware -- /auth/me, for
# instance, is deliberately cheap and does not need throttling beyond what the
# login limit already provides.
RateLimitedUser = Annotated[User, Depends(enforce_user_limit)]

# Applied with Depends() in the decorator rather than as a parameter, since the
# handler has no use for its return value.
AuthIpRateLimit = Depends(enforce_auth_ip_limit)
