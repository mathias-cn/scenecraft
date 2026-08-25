from functools import lru_cache
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from pydantic import Field
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

    database_url: str
    database_url_migrations: str
    redis_url: str = "redis://redis:6379/0"

    higgsfield_api_key: str = ""
    elevenlabs_api_key: str = ""
    openai_api_key: str = ""

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
    cloudflare_api_token: str = ""

    cors_origins: str = "http://localhost:3000"

    celery_loglevel: str = "info"
    celery_task_max_retries: int = Field(default=2, ge=0, le=10)
    celery_retry_backoff_base: int = Field(default=2, ge=1, le=60)

    celery_concurrency_transcribe: int = Field(default=2, ge=1, le=32)
    celery_concurrency_scene_planning: int = Field(default=2, ge=1, le=32)
    celery_concurrency_media_gen: int = Field(default=1, ge=1, le=32)
    celery_concurrency_audio_gen: int = Field(default=2, ge=1, le=32)
    celery_concurrency_render: int = Field(default=1, ge=1, le=32)
    celery_concurrency_thumbnail: int = Field(default=2, ge=1, le=32)
    celery_concurrency_description: int = Field(default=2, ge=1, le=32)
    celery_concurrency_upload: int = Field(default=1, ge=1, le=32)

    rate_limit_window_seconds: int = Field(default=60, ge=1)
    rate_limit_transcribe: int = Field(default=20, ge=1)
    rate_limit_scene_planning: int = Field(default=20, ge=1)
    rate_limit_media_gen: int = Field(default=4, ge=1)
    rate_limit_audio_gen: int = Field(default=10, ge=1)
    rate_limit_render: int = Field(default=2, ge=1)
    rate_limit_thumbnail: int = Field(default=10, ge=1)
    rate_limit_description: int = Field(default=20, ge=1)
    rate_limit_upload: int = Field(default=6, ge=1)

    provider_concurrency_higgsfield: int = Field(default=2, ge=1, le=32)
    provider_concurrency_elevenlabs: int = Field(default=3, ge=1, le=32)
    provider_concurrency_openai: int = Field(default=4, ge=1, le=32)
    provider_concurrency_youtube: int = Field(default=1, ge=1, le=32)
    provider_concurrency_r2: int = Field(default=4, ge=1, le=32)

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

    @property
    def celery_broker_url(self) -> str:
        return self.redis_url

    @property
    def celery_result_backend(self) -> str:
        return self.redis_url

    def concurrency_for(self, queue: str) -> int:
        name = getattr(queue, "value", queue)
        return getattr(self, f"celery_concurrency_{name}")

    def rate_limit_for(self, queue: str) -> int:
        name = getattr(queue, "value", queue)
        return getattr(self, f"rate_limit_{name}")

    def provider_concurrency_for(self, provider: str) -> int:
        name = provider.strip().lower()
        attr = f"provider_concurrency_{name}"
        if hasattr(self, attr):
            return getattr(self, attr)
        return 2


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
