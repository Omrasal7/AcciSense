from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import contacts, health, incidents
from app.core.config import get_settings
from app.repositories.incident_repository import IncidentRepository


settings = get_settings()
app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

repository = IncidentRepository(settings.database_path)
repository.initialize()

app.state.repository = repository

app.include_router(health.router, prefix="/api/v1")
app.include_router(incidents.router, prefix="/api/v1")
app.include_router(contacts.router, prefix="/api/v1")

settings.upload_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(settings.upload_dir)), name="uploads")
