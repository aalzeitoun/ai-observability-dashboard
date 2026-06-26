from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


InferenceProfile = Literal["manual", "normal", "drift"]
DriftProfile = Literal["all", "manual", "normal", "drift"]
AlertSeverity = Literal["info", "warning", "critical"]
AlertStatus = Literal["ok", "info", "warning", "critical"]


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


class BatchSimulationResponse(BaseModel):
    profile: InferenceProfile
    requested_count: int
    inserted_count: int
    first_log_id: int | None
    last_log_id: int | None


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


class DriftFeatureResult(BaseModel):
    feature_name: str
    reference_sample_count: int
    production_sample_count: int
    reference_mean: float | None
    production_mean: float | None
    ks_statistic: float | None
    p_value: float | None
    drift_detected: bool
    insufficient_data: bool


class DriftReport(BaseModel):
    dataset_name: str
    profile: DriftProfile
    production_limit: int
    alpha: float
    min_samples: int
    drift_detected: bool
    features: list[DriftFeatureResult]


class AlertItem(BaseModel):
    name: str
    severity: AlertSeverity
    message: str
    metric_value: float | int | None
    threshold: float | int | None


class AlertEvaluationWindow(BaseModel):
    recent_log_limit: int
    latest_log_at: datetime | None


class AlertThresholds(BaseModel):
    latency_p95_threshold_ms: float
    avg_confidence_threshold: float
    low_confidence_threshold: float
    drift_alpha: float
    drift_min_samples: int


class AlertMetrics(BaseModel):
    total_logs: int
    avg_latency_ms: float | None
    p95_latency_ms: float | None
    max_latency_ms: float | None
    avg_confidence: float | None
    low_confidence_count: int
    latest_log_at: datetime | None


class AlertSummary(BaseModel):
    status: AlertStatus
    alert_count: int
    critical_count: int
    warning_count: int
    info_count: int
    evaluation_window: AlertEvaluationWindow
    thresholds: AlertThresholds
    metrics: AlertMetrics
    alerts: list[AlertItem]
