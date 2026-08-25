from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
import app.models  # noqa: F401 — register SQLAlchemy metadata


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield


app = FastAPI(
    title="SceneCraft",
    description="API de geração automatizada de vídeos para YouTube",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
