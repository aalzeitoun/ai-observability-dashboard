from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_endpoint_returns_ok():
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()

    assert body["status"] == "ok"
    assert body["service"] == "ai-observability-backend"


def test_reference_data_summary_contains_iris_features():
    response = client.get("/reference-data/summary")

    assert response.status_code == 200
    body = response.json()

    assert body["dataset_name"] == "iris_training"
    assert body["total_features"] == 4
    assert body["total_values"] == 600

    feature_names = {feature["feature_name"] for feature in body["features"]}

    assert feature_names == {
        "sepal_length",
        "sepal_width",
        "petal_length",
        "petal_width",
    }


def test_manual_inference_log_can_be_created():
    request_id = f"test-{uuid4()}"

    payload = {
        "request_id": request_id,
        "model_name": "test-model",
        "features": {
            "sepal_length": 5.1,
            "sepal_width": 3.5,
            "petal_length": 1.4,
            "petal_width": 0.2,
        },
        "prediction": 0,
        "confidence": 0.97,
        "latency_ms": 18.4,
    }

    response = client.post("/inference-logs", json=payload)

    assert response.status_code == 201
    body = response.json()

    assert body["request_id"] == request_id
    assert body["profile"] == "manual"
    assert body["confidence"] == 0.97
    assert body["latency_ms"] == 18.4


def test_simulate_inference_creates_normal_log():
    response = client.post("/simulate-inference?profile=normal")

    assert response.status_code == 201
    body = response.json()

    assert body["profile"] == "normal"
    assert body["model_name"] == "iris-logistic-regression"
    assert body["prediction_label"] in ["setosa", "versicolor", "virginica"]
    assert 0 <= body["confidence"] <= 1
    assert body["latency_ms"] >= 0


def test_simulate_batch_creates_multiple_logs():
    response = client.post("/simulate-batch?profile=drift&count=3")

    assert response.status_code == 201
    body = response.json()

    assert body["profile"] == "drift"
    assert body["requested_count"] == 3
    assert body["inserted_count"] == 3
    assert body["first_log_id"] is not None
    assert body["last_log_id"] is not None


def test_metrics_summary_has_expected_shape():
    response = client.get("/metrics/summary")

    assert response.status_code == 200
    body = response.json()

    assert "total_logs" in body
    assert "avg_latency_ms" in body
    assert "p95_latency_ms" in body
    assert "avg_confidence" in body
    assert body["total_logs"] >= 0


def test_drift_endpoint_has_feature_results():
    response = client.get("/drift/ks?profile=all&limit=100&min_samples=2")

    assert response.status_code == 200
    body = response.json()

    assert body["dataset_name"] == "iris_training"
    assert body["profile"] == "all"
    assert len(body["features"]) == 4

    for feature in body["features"]:
        assert "feature_name" in feature
        assert "reference_sample_count" in feature
        assert "production_sample_count" in feature
        assert "drift_detected" in feature


def test_alerts_endpoint_has_expected_shape():
    response = client.get("/alerts/current?limit=100")

    assert response.status_code == 200
    body = response.json()

    assert body["status"] in ["ok", "info", "warning", "critical"]
    assert "alert_count" in body
    assert "thresholds" in body
    assert "metrics" in body
    assert "alerts" in body
