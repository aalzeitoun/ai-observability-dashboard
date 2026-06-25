import os
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb

from app.db import get_db_connection, init_db
from app.model import model_simulator
from app.reference_data import fetch_reference_summary, seed_reference_data
from app.schemas import (
    InferenceLogCreate,
    InferenceLogRead,
    MetricPoint,
    MetricsSummary,
    ModelInfo,
    PredictionCount,
    ReferenceDataSummary,
    SimulatedInferenceResponse,
)
from app.websocket_manager import ConnectionManager


manager = ConnectionManager()


def get_cors_origins() -> list[str]:
    raw_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173")
    return [origin.strip() for origin in raw_origins.split(",") if origin.strip()]


def round_optional(value: float | None, digits: int = 4) -> float | None:
    if value is None:
        return None

    return round(float(value), digits)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    seed_reference_data()
    yield


app = FastAPI(
    title="AI Observability & MLOps Dashboard API",
    version="0.8.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def insert_inference_log(payload: InferenceLogCreate) -> dict:
    insert_sql = """
    INSERT INTO inference_logs (
        request_id,
        model_name,
        features,
        prediction,
        confidence,
        latency_ms,
        profile
    )
    VALUES (
        %(request_id)s,
        %(model_name)s,
        %(features)s,
        %(prediction)s,
        %(confidence)s,
        %(latency_ms)s,
        %(profile)s
    )
    RETURNING
        id,
        request_id,
        model_name,
        features,
        prediction,
        confidence,
        latency_ms,
        profile,
        created_at;
    """

    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                insert_sql,
                {
                    "request_id": payload.request_id,
                    "model_name": payload.model_name,
                    "features": Jsonb(payload.features),
                    "prediction": payload.prediction,
                    "confidence": payload.confidence,
                    "latency_ms": payload.latency_ms,
                    "profile": payload.profile,
                },
            )
            row = cursor.fetchone()

        connection.commit()

    return row


def fetch_inference_logs(limit: int = 20) -> list[dict]:
    select_sql = """
    SELECT
        id,
        request_id,
        model_name,
        features,
        prediction,
        confidence,
        latency_ms,
        profile,
        created_at
    FROM inference_logs
    ORDER BY created_at DESC
    LIMIT %(limit)s;
    """

    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(select_sql, {"limit": limit})
            rows = cursor.fetchall()

    return rows


def fetch_metrics_summary() -> dict:
    summary_sql = """
    SELECT
        COUNT(*) AS total_logs,
        AVG(latency_ms) AS avg_latency_ms,
        percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95_latency_ms,
        MAX(latency_ms) AS max_latency_ms,
        AVG(confidence) AS avg_confidence,
        SUM(CASE WHEN confidence < 0.80 THEN 1 ELSE 0 END) AS low_confidence_count,
        MAX(created_at) AS latest_log_at
    FROM inference_logs;
    """

    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(summary_sql)
            row = cursor.fetchone()

    return {
        "total_logs": int(row["total_logs"] or 0),
        "avg_latency_ms": round_optional(row["avg_latency_ms"], 2),
        "p95_latency_ms": round_optional(row["p95_latency_ms"], 2),
        "max_latency_ms": round_optional(row["max_latency_ms"], 2),
        "avg_confidence": round_optional(row["avg_confidence"], 4),
        "low_confidence_count": int(row["low_confidence_count"] or 0),
        "latest_log_at": row["latest_log_at"],
    }


def fetch_prediction_counts() -> list[dict]:
    prediction_sql = """
    SELECT
        prediction,
        COUNT(*) AS count,
        AVG(confidence) AS avg_confidence
    FROM inference_logs
    GROUP BY prediction
    ORDER BY prediction ASC;
    """

    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(prediction_sql)
            rows = cursor.fetchall()

    return [
        {
            "prediction": int(row["prediction"]),
            "count": int(row["count"]),
            "avg_confidence": round_optional(row["avg_confidence"], 4),
        }
        for row in rows
    ]


def fetch_metrics_timeseries(limit: int = 50) -> list[dict]:
    timeseries_sql = """
    SELECT
        id,
        created_at,
        latency_ms,
        confidence,
        prediction
    FROM inference_logs
    ORDER BY created_at DESC
    LIMIT %(limit)s;
    """

    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(timeseries_sql, {"limit": limit})
            rows = cursor.fetchall()

    return list(reversed(rows))


def build_dashboard_snapshot() -> dict:
    return {
        "type": "dashboard_snapshot",
        "summary": fetch_metrics_summary(),
        "predictions": fetch_prediction_counts(),
        "timeseries": fetch_metrics_timeseries(limit=50),
        "recent_logs": fetch_inference_logs(limit=10),
    }


async def broadcast_dashboard_snapshot() -> None:
    snapshot = build_dashboard_snapshot()
    await manager.broadcast_json(jsonable_encoder(snapshot))


@app.websocket("/ws/dashboard")
async def dashboard_websocket(websocket: WebSocket) -> None:
    await manager.connect(websocket)

    try:
        await websocket.send_json(jsonable_encoder(build_dashboard_snapshot()))

        while True:
            await websocket.receive_text()

    except WebSocketDisconnect:
        pass

    finally:
        manager.disconnect(websocket)


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "ai-observability-backend",
        "version": "0.8.0",
    }


@app.get("/health/db")
def database_health() -> dict[str, str | int]:
    try:
        with get_db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 AS result;")
                row = cursor.fetchone()

        return {
            "status": "ok",
            "database": "postgresql",
            "result": row["result"] if row else 0,
        }

    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "error",
                "database": "postgresql",
                "message": str(exc),
            },
        ) from exc


@app.get("/model/info", response_model=ModelInfo)
def get_model_info() -> dict:
    return model_simulator.info()

@app.get("/reference-data/summary", response_model=ReferenceDataSummary)
def get_reference_data_summary() -> dict:
    try:
        return fetch_reference_summary()

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc
        

@app.post("/inference-logs", response_model=InferenceLogRead, status_code=201)
def create_inference_log(
    payload: InferenceLogCreate,
    background_tasks: BackgroundTasks,
) -> dict:
    try:
        inserted_log = insert_inference_log(payload)
        background_tasks.add_task(broadcast_dashboard_snapshot)

        return inserted_log

    except UniqueViolation as exc:
        raise HTTPException(
            status_code=409,
            detail=f"request_id already exists: {payload.request_id}",
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc


@app.get("/inference-logs", response_model=list[InferenceLogRead])
def list_inference_logs(
    limit: int = Query(default=20, ge=1, le=100),
) -> list[dict]:
    try:
        return fetch_inference_logs(limit=limit)

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc


@app.post("/simulate-inference", response_model=SimulatedInferenceResponse, status_code=201)
def simulate_inference(
    background_tasks: BackgroundTasks,
    profile: Literal["normal", "drift"] = "normal",
) -> dict:
    simulated = model_simulator.simulate(profile=profile)

    payload = InferenceLogCreate(
        request_id=simulated["request_id"],
        model_name=simulated["model_name"],
        features=simulated["features"],
        prediction=simulated["prediction"],
        confidence=simulated["confidence"],
        latency_ms=simulated["latency_ms"],
        profile=simulated["profile"],
    )

    try:
        inserted_log = insert_inference_log(payload)
        background_tasks.add_task(broadcast_dashboard_snapshot)

        return {
            **inserted_log,
            "prediction_label": simulated["prediction_label"],
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc


@app.get("/metrics/summary", response_model=MetricsSummary)
def get_metrics_summary() -> dict:
    try:
        return fetch_metrics_summary()

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc


@app.get("/metrics/predictions", response_model=list[PredictionCount])
def get_prediction_counts() -> list[dict]:
    try:
        return fetch_prediction_counts()

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc


@app.get("/metrics/timeseries", response_model=list[MetricPoint])
def get_metrics_timeseries(
    limit: int = Query(default=50, ge=1, le=200),
) -> list[dict]:
    try:
        return fetch_metrics_timeseries(limit=limit)

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc
