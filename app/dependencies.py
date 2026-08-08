"""The authentication dependency.

Everything an endpoint needs to say "this route requires a logged-in user"
lives here, as a single injectable that yields the User or refuses the request.
"""

from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User
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
        raise _unauthenticated()

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
