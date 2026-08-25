from datetime import datetime

from pydantic import BaseModel, Field

from app.models.job import JobStatus


class JobCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    prompt: str = Field(min_length=1, max_length=8000)


class JobRead(BaseModel):
    id: str
    title: str
    prompt: str
    status: JobStatus
    script: str | None = None
    voice_url: str | None = None
    video_url: str | None = None
    youtube_url: str | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
