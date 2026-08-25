from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://scenecraft:scenecraft@postgres:5432/scenecraft"
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


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
