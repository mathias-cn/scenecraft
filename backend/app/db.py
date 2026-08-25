from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import postgres_connect_args, settings


class Base(DeclarativeBase):
    pass


engine = create_engine(
    settings.database_url_ssl,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    connect_args=postgres_connect_args(settings.database_url),
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
