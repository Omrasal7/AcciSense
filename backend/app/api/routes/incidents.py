from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from app.core.config import get_settings
from app.schemas.incident import AnalyzeResponse, IncidentRead
from app.services.orchestrator import AccidentPipeline


router = APIRouter(tags=["incidents"])


@router.get("/incidents", response_model=list[IncidentRead])
def list_incidents(request: Request) -> list[dict]:
    return request.app.state.repository.list_incidents()


@router.get("/incidents/{incident_id}", response_model=IncidentRead)
def get_incident(incident_id: str, request: Request) -> dict:
    incident = request.app.state.repository.get_incident(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident


@router.delete("/incidents/{incident_id}")
def delete_incident(incident_id: str, request: Request) -> dict:
    incident = request.app.state.repository.delete_incident(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")

    _delete_uploaded_file(incident.get("image_url"))
    _delete_uploaded_file(incident.get("original_media_url"))
    return {"deleted": True, "incident_id": incident_id}


@router.post("/incidents/analyze", response_model=AnalyzeResponse)
async def analyze_incident(
    request: Request,
    image: UploadFile = File(...),
    latitude: float | None = Form(default=None),
    longitude: float | None = Form(default=None),
    source_id: str | None = Form(default=None),
) -> dict:
    contents = await image.read()
    pipeline = AccidentPipeline(get_settings(), request.app.state.repository)
    try:
        incident = pipeline.analyze(
            image_bytes=contents,
            filename=image.filename or "incident.jpg",
            latitude=latitude,
            longitude=longitude,
            source_id=source_id,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"incident": incident}


def _delete_uploaded_file(relative_path: str | None) -> None:
    if not relative_path:
        return
    file_name = Path(relative_path).name
    file_path = get_settings().upload_dir / file_name
    if file_path.exists():
        file_path.unlink()
