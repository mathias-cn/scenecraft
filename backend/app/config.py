from functools import lru_cache
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from pydantic_settings import BaseSettings, SettingsConfigDict


def ensure_sslmode(url: str, mode: str = "require") -> str:
    """Append sslmode=require when the DSN does not already set it (Supabase exige SSL)."""
    parsed = urlparse(url)
    query = parse_qsl(parsed.query, keep_blank_values=True)
    if not any(key.lower() == "sslmode" for key, _ in query):
        query.append(("sslmode", mode))
    return urlunparse(parsed._replace(query=urlencode(query)))


def postgres_connect_args(url: str) -> dict[str, str]:
    """Pass sslmode to libpq. Defaults to require; an explicit sslmode= in the URL wins."""
    params = dict(parse_qsl(urlparse(ensure_sslmode(url)).query))
    return {"sslmode": params.get("sslmode", "require")}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    # Pooler Supabase (porta 6543) — FastAPI e Celery
    database_url: str
    # Conexão direta Supabase (porta 5432) — só Alembic
    database_url_migrations: str
    redis_url: str = "redis://redis:6379/0"

    higgsfield_api_key: str = ""
    elevenlabs_api_key: str = ""
    anthropic_api_key: str = ""

    youtube_client_id: str = ""
    youtube_client_secret: str = ""
    youtube_refresh_token: str = ""

    s3_bucket: str = ""
    s3_region: str = "auto"
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_endpoint_url: str = ""
    r2_account_id: str = ""
    r2_public_base_url: str = ""

    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def object_storage_endpoint(self) -> str:
        if self.s3_endpoint_url:
            return self.s3_endpoint_url
        if self.r2_account_id:
            return f"https://{self.r2_account_id}.r2.cloudflarestorage.com"
        return ""

    @property
    def database_url_ssl(self) -> str:
        return ensure_sslmode(self.database_url)

    @property
    def database_url_migrations_ssl(self) -> str:
        return ensure_sslmode(self.database_url_migrations)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
