from enum import Enum as PyEnum

from sqlalchemy import Enum as SAEnum


def pg_enum(enum_cls: type[PyEnum], name: str) -> SAEnum:
    """Postgres native ENUM owned by Alembic (`create_type=False`)."""
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=True,
        create_type=False,
        values_callable=lambda members: [item.value for item in members],
    )
