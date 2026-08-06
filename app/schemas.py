import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
