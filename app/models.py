import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)

    # The bcrypt output string, which carries its own algorithm, cost, and
    # salt -- see app/security.py. 60 chars today; String(255) leaves room to
    # migrate to argon2 later without another column change.
    #
    # Named password_hash, not password, so that no one reading a query result
    # or a log line can mistake this for something reversible.
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    # Nullable because registration takes email and password only. There is no
    # endpoint that collects a display name yet, so requiring one here would
    # mean inventing a value at signup -- and a derived default like the email
    # local-part is a product decision, not a schema one. Left NULL until some
    # future ticket adds a profile endpoint to fill it in.
    display_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    children: Mapped[list["Child"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Child(Base):
    __tablename__ = "children"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped["User"] = relationship(back_populates="children")
    quotes: Mapped[list["Quote"]] = relationship(back_populates="child")


class Quote(Base):
    __tablename__ = "quotes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    child_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("children.id", ondelete="CASCADE"), nullable=False, index=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    said_on: Mapped[date] = mapped_column(
        Date, nullable=False, server_default=func.current_date()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    child: Mapped["Child"] = relationship(back_populates="quotes")

    __table_args__ = (
        CheckConstraint(
            "length(btrim(text)) > 0", name="ck_quotes_text_not_blank"
        ),
    )
