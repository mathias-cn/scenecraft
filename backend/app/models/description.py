from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import DescriptionSource
from app.models.mixins import ProjectFKMixin, UUIDPrimaryKeyMixin
from app.models.pg import pg_enum

if TYPE_CHECKING:
    from app.models.project import Project


class Description(UUIDPrimaryKeyMixin, ProjectFKMixin, Base):
    __tablename__ = "descriptions"

    text: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[DescriptionSource] = mapped_column(
        pg_enum(DescriptionSource, "description_source"), nullable=False
    )

    project: Mapped[Project] = relationship(back_populates="descriptions")
