from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    test_database_url: str | None = None

    # --- Auth -------------------------------------------------------------
    #
    # jwt_secret deliberately has NO default value.
    #
    # This is the most important line in this file. A JWT is not encrypted, it
    # is *signed*: the signature is what proves the token came from us and was
    # not tampered with. That proof rests entirely on this secret staying
    # secret. Anyone holding it can mint a token claiming to be any user, and
    # the API will accept it, because the signature will check out.
    #
    # If this field had a default -- say "changeme" -- the app would boot
    # happily in production with a secret sitting in a public GitHub
    # repository, and nothing would look wrong. By leaving it required,
    # Pydantic raises a ValidationError at import time and the process refuses
    # to start. A crash on deploy is a bad afternoon; a forgeable token is a
    # breach you might not notice for months.
    jwt_secret: str

    # HS256 is symmetric: the same secret both signs and verifies. That fits
    # here because one service does both jobs.
    #
    # The alternative, RS256, is asymmetric -- a private key signs, a public
    # key verifies. You reach for that when some *other* service needs to
    # verify our tokens without being trusted to create them, since the public
    # key can be handed out freely. We have no such service, so the extra key
    # management would buy nothing.
    jwt_algorithm: str = "HS256"

    # Short expiry, for a reason that is a real limitation rather than caution.
    #
    # JWTs are stateless. There is no server-side session record, which is
    # exactly what makes them scale -- any instance can verify a token with no
    # database lookup. The cost of that: we cannot revoke one. A signed token
    # stays valid until it expires, full stop. Logging out, changing a
    # password, deleting an account -- none of it invalidates a token that has
    # already been issued and is sitting in someone's browser.
    #
    # So expiry is the ONLY revocation mechanism we have, and the window is
    # the blast radius of a stolen token. 30 minutes keeps that small.
    #
    # The usual fix is a refresh-token pair: a short-lived access token plus a
    # long-lived refresh token that IS stored server-side and therefore can be
    # revoked. That is explicitly out of scope for QJ-2, which is precisely
    # why the access token has to stay short on its own.
    access_token_expire_minutes: int = 30


settings = Settings()
