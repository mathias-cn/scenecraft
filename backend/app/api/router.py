from fastapi import APIRouter

from app.api import ai, characters, costs, health, image_models, jobs, projects, styles

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(ai.router)
api_router.include_router(image_models.router)
api_router.include_router(projects.router)
api_router.include_router(jobs.router)
api_router.include_router(styles.router)
api_router.include_router(characters.router)
api_router.include_router(costs.router)
