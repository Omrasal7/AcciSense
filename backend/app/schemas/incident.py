from datetime import datetime
from pydantic import BaseModel, Field


class DetectionResult(BaseModel):
    accident_detected: bool
    confidence: float
    model_used: str
    evidence: list[str]


class SeverityResult(BaseModel):
    label: str
    score: int
    confidence: float
    model_used: str
    rationale: list[str]


class LocationResult(BaseModel):
    latitude: float | None = None
    longitude: float | None = None
    source: str
    address: str | None = None
    google_maps_url: str | None = None
    osm_url: str | None = None
    nearest_hospitals: list[dict] = Field(default_factory=list)
    nearest_police_stations: list[dict] = Field(default_factory=list)


class NotificationResult(BaseModel):
    sms_sent_to: list[str] = Field(default_factory=list)
    sms_results: list[dict] = Field(default_factory=list)
    email_sent_to: list[str] = Field(default_factory=list)
    dashboard_logged: bool = True
    errors: list[str] = Field(default_factory=list)


class IncidentRead(BaseModel):
    id: str
    created_at: datetime
    media_type: str
    original_media_url: str
    image_url: str
    detection: DetectionResult
    severity: SeverityResult
    location: LocationResult
    notifications: NotificationResult


class AnalyzeResponse(BaseModel):
    incident: IncidentRead
