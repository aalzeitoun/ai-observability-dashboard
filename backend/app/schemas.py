from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


InferenceProfile = Literal["manual", "normal", "drift"]


class InferenceLogCreate(BaseModel):
    request_id: str = Field(..., min_length=1, max_length=100)
    model_name: str = Field(..., min_length=1, max_length=100)
    features: dict[str, Any]
    prediction: int
    confidence: float = Field(..., ge=0, le=1)
    latency_ms: float = Field(..., ge=0)
    profile: InferenceProfile = "manual"


class InferenceLogRead(BaseModel):
    id: int
    request_id: str
    model_name: str
    features: dict[str, Any]
    prediction: int
    confidence: float
    latency_ms: float
    profile: InferenceProfile
    created_at: datetime


class ModelInfo(BaseModel):
    model_name: str
    dataset: str
    features: list[str]
    target_labels: list[str]
    simulated_profiles: list[str]


class SimulatedInferenceResponse(InferenceLogRead):
    prediction_label: str


class MetricsSummary(BaseModel):
    total_logs: int
    avg_latency_ms: float | None
    p95_latency_ms: float | None
    max_latency_ms: float | None
    avg_confidence: float | None
    low_confidence_count: int
    latest_log_at: datetime | None


class PredictionCount(BaseModel):
    prediction: int
    count: int
    avg_confidence: float | None


class MetricPoint(BaseModel):
    id: int
    created_at: datetime
    latency_ms: float
    confidence: float
    prediction: int


class ReferenceFeatureSummary(BaseModel):
    feature_name: str
    sample_count: int
    mean_value: float
    min_value: float
    max_value: float


class ReferenceDataSummary(BaseModel):
    dataset_name: str
    total_features: int
    total_values: int
    features: list[ReferenceFeatureSummary]
