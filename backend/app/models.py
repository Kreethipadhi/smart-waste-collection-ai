from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, Field, field_validator

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

class WasteType(str, Enum):
    general = 'general'
    recyclable = 'recyclable'
    organic = 'organic'

class Priority(str, Enum):
    normal = 'normal'
    watch = 'watch'
    high = 'high'
    critical = 'critical'

class RouteStatus(str, Enum):
    planned = 'planned'
    approved = 'approved'
    in_progress = 'in_progress'
    collected = 'collected'
    verified = 'verified'
    rejected = 'rejected'

class Bin(BaseModel):
    id: str
    zone: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    waste_type: WasteType
    capacity_liters: float = Field(gt=0)
    fill_percent: float = Field(ge=0, le=100)
    threshold_percent: float = Field(default=85, ge=1, le=100)
    sensor_status: str = 'healthy'
    sensor_id: str = ''
    last_seen: datetime = Field(default_factory=utcnow)
    last_collection: datetime | None = None

class Vehicle(BaseModel):
    id: str
    capacity_liters: float = Field(gt=0)
    current_load_liters: float = Field(default=0, ge=0)
    supported_waste: list[WasteType]
    latitude: float
    longitude: float
    status: str = 'available'

class SensorReading(BaseModel):
    bin_id: str
    fill_percent: float = Field(ge=0, le=100)
    timestamp: datetime = Field(default_factory=utcnow)
    weight_kg: float | None = Field(default=None, ge=0)
    temperature_c: float | None = Field(default=None, ge=-50, le=100)

    @field_validator('timestamp')
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

class Forecast(BaseModel):
    bin_id: str
    predicted_percent: float
    hours_to_threshold: float | None
    daily_growth_points: float
    method: str = 'linear time-series trend'
    confidence: float

class PriorityDecision(BaseModel):
    bin_id: str
    priority: Priority
    score: float
    explanation: str
    forecast: Forecast

class RoutePlan(BaseModel):
    id: str
    vehicle_id: str
    waste_type: WasteType
    bin_ids: list[str]
    estimated_load_liters: float
    estimated_distance_km: float
    estimated_minutes: int
    status: RouteStatus = RouteStatus.planned
    created_at: datetime = Field(default_factory=utcnow)
    operator_comment: str = ''

class AgentEvent(BaseModel):
    id: str
    workflow_id: str
    agent: str
    stage: str
    status: str
    created_at: datetime = Field(default_factory=utcnow)
    input: dict = Field(default_factory=dict)
    output: dict = Field(default_factory=dict)
    explanation: str = ''

class WorkflowResult(BaseModel):
    workflow_id: str
    status: str
    priorities: list[PriorityDecision]
    routes: list[RoutePlan]
    reviewer_feedback: list[str]
    events: list[AgentEvent]

class ApprovalRequest(BaseModel):
    approved: bool
    comment: str = ''

class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=1024)
