from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Numeric, Text, text as sql_text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import DescriptionSource
from app.models.mixins import ProjectFKMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.pg import pg_enum

if TYPE_CHECKING:
    from app.models.project import Project


class Description(UUIDPrimaryKeyMixin, ProjectFKMixin, TimestampMixin, Base):
    __tablename__ = "descriptions"

    text: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        default=list,
        server_default=sql_text("'{}'::text[]"),
    )
    source: Mapped[DescriptionSource] = mapped_column(
        pg_enum(DescriptionSource, "description_source"), nullable=False
    )
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)

    project: Mapped[Project] = relationship(back_populates="descriptions")
