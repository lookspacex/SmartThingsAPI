from __future__ import annotations

import datetime as dt
import uuid
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    api_key_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc))

    smartthings_token: Mapped["SmartThingsToken"] = relationship(back_populates="user", uselist=False)


class SmartThingsToken(Base):
    __tablename__ = "smartthings_tokens"
    __table_args__ = (UniqueConstraint("user_id", name="uq_smartthings_tokens_user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True)

    access_token: Mapped[str] = mapped_column(String(4096))
    refresh_token: Mapped[str] = mapped_column(String(4096), default="")
    token_type: Mapped[str] = mapped_column(String(64), default="Bearer")
    scope: Mapped[str] = mapped_column(String(2048), default="")
    expires_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=lambda: dt.datetime.now(dt.timezone.utc))
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: dt.datetime.now(dt.timezone.utc),
        onupdate=lambda: dt.datetime.now(dt.timezone.utc),
    )

    user: Mapped[User] = relationship(back_populates="smartthings_token")

