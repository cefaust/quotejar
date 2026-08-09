"""Application settings.

Everything in this module runs exactly once, at import.

That is the entire point, and it is worth being explicit about because Lambda
makes the distinction expensive. A Lambda container is reused across
invocations: module-level code runs once per *cold start*, handler code runs
once per *request*. Put the Secrets Manager call inside the handler and every
single request pays a network round-trip to Secrets Manager -- tens of
milliseconds added to every response, plus a per-API-call charge that is
invisible at ten requests and a real line item at ten million.

So the resolution below happens here, at module scope, where it is amortised
across every warm invocation. The same reasoning governs the SQLAlchemy engine
in app/db.py.
"""

import os

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _from_secrets_manager(secret_id: str) -> str:
    """Read one secret value.

    boto3 is imported here rather than at module top on purpose. The Lambda
    base image bundles boto3 (1.42.97 at time of writing), so adding it to
    requirements.txt would duplicate roughly 70 MB into the image for no gain.
    Locally we resolve config from environment variables and never reach this
    function, so the import cost is never paid outside Lambda.

    No error handling. If a secret cannot be read the process must not start:
    a container that boots without its database URL would come up, fail every
    request, and look like an application bug rather than a permissions one.
    Crashing at import surfaces the real cause in the cold-start logs.
    """
    import boto3

    client = boto3.client("secretsmanager")
    return client.get_secret_value(SecretId=secret_id)["SecretString"]


def _resolve(env_name: str, secret_env_name: str) -> str | None:
    """Take the value from the environment, or fetch the secret it names.

    Two sources, in priority order:

      1. The value itself, e.g. DATABASE_URL -- used locally and in tests.
      2. A secret *identifier*, e.g. DATABASE_URL_SECRET_ID -- used in Lambda,
         where the environment holds the name of a secret rather than the
         secret.

    The direct value wins so a local override always beats a remote fetch,
    which keeps tests hermetic and makes it possible to point a container at a
    scratch database without touching AWS.

    Note what is deliberately *not* in the Lambda environment: the secret
    itself. Lambda environment variables are visible to anyone with
    lambda:GetFunctionConfiguration and are shown in the console, so a
    database password pasted into one is a password shared with every reader
    of that page. Storing only the identifier means the value is fetched over
    an authenticated API call, governed by IAM, and never displayed.
    """
    direct = os.environ.get(env_name)
    if direct:
        return direct

    secret_id = os.environ.get(secret_env_name)
    if secret_id:
        return _from_secrets_manager(secret_id)

    return None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    test_database_url: str | None = None

    # --- Auth -------------------------------------------------------------
    #
    # jwt_secret deliberately has NO default value.
    #
    # A JWT is not encrypted, it is *signed*: the signature is what proves the
    # token came from us and was not tampered with. That proof rests entirely
    # on this secret staying secret. Anyone holding it can mint a token
    # claiming to be any user, and the API will accept it.
    #
    # If this had a default -- say "changeme" -- the app would boot happily in
    # production with a secret sitting in a public GitHub repository, and
    # nothing would look wrong. Required means the process refuses to start.
    #
    # The 32-character floor is RFC 7518 section 3.2: an HMAC key should be at
    # least as long as the hash it feeds, and SHA-256 outputs 32 bytes.
    # Cracking the secret offline forges tokens for every account at once,
    # which is far better value to an attacker than cracking one password.
    jwt_secret: str = Field(min_length=32)

    # HS256 is symmetric: the same secret signs and verifies, which fits
    # because one service does both jobs. RS256 would only pay off if another
    # service had to verify without being trusted to issue.
    jwt_algorithm: str = "HS256"

    # JWTs are stateless and therefore cannot be revoked. A signed token stays
    # valid until it expires -- logging out, changing a password, or deleting
    # an account does not invalidate one already issued. Expiry is the only
    # revocation mechanism we have, so the window is the blast radius of a
    # stolen token. Refresh tokens are out of scope, which is precisely why
    # the access token has to stay short on its own.
    access_token_expire_minutes: int = 30

    # --- Connection pooling -----------------------------------------------
    #
    # Sized against the database, not against the application. See app/db.py
    # for the arithmetic; the short version is that db.t4g.micro allows 79
    # connections total, and the deployment must not be able to exhaust them.
    db_pool_size: int = 1
    db_max_overflow: int = 1


# Resolved once, at import. In Lambda this is the cold start; in a container
# or locally it is process startup. Either way, never per request.
_resolved = {
    "database_url": _resolve("DATABASE_URL", "DATABASE_URL_SECRET_ID"),
    "jwt_secret": _resolve("JWT_SECRET", "JWT_SECRET_SECRET_ID"),
}

settings = Settings(**{k: v for k, v in _resolved.items() if v is not None})
