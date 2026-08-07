import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.security import MAX_PASSWORD_BYTES


class QuoteCreate(BaseModel):
    child_id: uuid.UUID
    text: str = Field(min_length=1, max_length=2000)
    said_on: date | None = None

    @field_validator("text")
    @classmethod
    def text_must_not_be_blank(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("text must not be blank")
        return cleaned


class QuoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    child_id: uuid.UUID
    text: str
    said_on: date
    created_at: datetime
    updated_at: datetime


class QuotePage(BaseModel):
    items: list[QuoteRead]
    total: int
    limit: int
    offset: int


class UserCreate(BaseModel):
    """Registration payload. Email and password only."""

    email: EmailStr

    # The lower bound is a floor, not a policy. Length is the single biggest
    # factor in how long a password survives offline cracking, and 8 is the
    # usual minimum -- but "Password1!" satisfies every composition rule ever
    # written and is in every wordlist. Real strength checking means measuring
    # against known-breached corpora, which is its own ticket.
    #
    # The upper bound is not a policy at all -- it is bcrypt's hard limit.
    # bcrypt hashes at most 72 bytes and, since 4.x, raises ValueError beyond
    # that rather than truncating. Catching it here turns what would be a 500
    # into a 422 that names the field.
    #
    # Bytes, not characters, which is why this is a validator rather than
    # max_length: "é" is two bytes in UTF-8 and an emoji is four, so a
    # 40-character password can exceed 72 bytes. max_length counts characters
    # and would let those through to explode later.
    password: str = Field(min_length=8)

    @field_validator("password")
    @classmethod
    def password_fits_bcrypt(cls, v: str) -> str:
        if len(v.encode("utf-8")) > MAX_PASSWORD_BYTES:
            raise ValueError(
                f"password must be at most {MAX_PASSWORD_BYTES} bytes "
                "(note: accented characters and emoji count as more than one)"
            )
        return v


class UserRead(BaseModel):
    """A user as returned to clients.

    password_hash is absent, and its absence is the point. Response models in
    FastAPI are an allowlist: only fields declared here are serialised, so a
    handler that returns the whole ORM object still cannot leak the hash.
    That is a far safer default than remembering to strip it at each call
    site, because forgetting here fails closed rather than open.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    display_name: str | None
    created_at: datetime


class Token(BaseModel):
    """The token endpoint's response.

    The field names are not ours to choose. OAuth2 specifies access_token and
    token_type, and FastAPI's Swagger integration reads exactly those keys to
    wire up the Authorize button. Renaming them to something tidier would
    break the tooling that is the whole reason for using this shape.
    """

    access_token: str
    token_type: str = "bearer"
