from fastapi import APIRouter, HTTPException, Request

from app.core.config import get_settings
from app.services.camera_registry import CameraRegistry

from app.schemas.contact import ContactCreate, ContactRead


router = APIRouter(tags=["contacts"])


@router.get("/contacts", response_model=list[ContactRead])
def list_contacts(request: Request) -> list[dict]:
    return request.app.state.repository.list_contacts()


@router.post("/contacts", response_model=ContactRead)
def create_contact(payload: ContactCreate, request: Request) -> dict:
    return request.app.state.repository.create_contact(payload.model_dump())


@router.delete("/contacts/{contact_id}", response_model=ContactRead)
def delete_contact(contact_id: int, request: Request) -> dict:
    deleted = request.app.state.repository.delete_contact(contact_id)
    if deleted is None:
        raise HTTPException(status_code=404, detail="Admin contact not found")
    return deleted


@router.get("/camera-sources")
def list_camera_sources() -> list[dict]:
    registry = CameraRegistry(get_settings().camera_registry_path)
    return registry.list_sources()
