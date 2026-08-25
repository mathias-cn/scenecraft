from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.mixins import UUIDPrimaryKeyMixin, utcnow


class Style(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "styles"
    __table_args__ = (UniqueConstraint("slug", name="uq_styles_slug"),)

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        server_default=text("now()"),
        nullable=False,
    )
