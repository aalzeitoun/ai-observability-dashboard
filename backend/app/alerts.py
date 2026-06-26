from app.db import get_db_connection
from app.drift import build_ks_drift_report


DEFAULT_LATENCY_P95_THRESHOLD_MS = 100.0
DEFAULT_AVG_CONFIDENCE_THRESHOLD = 0.80
DEFAULT_LOW_CONFIDENCE_THRESHOLD = 0.70


def fetch_recent_alert_metrics(limit: int = 100) -> dict:
    metrics_sql = """
    WITH recent_logs AS (
        SELECT
            latency_ms,
            confidence,
            created_at
        FROM inference_logs
        ORDER BY created_at DESC
        LIMIT %(limit)s
    )
    SELECT
        COUNT(*) AS total_logs,
        AVG(latency_ms) AS avg_latency_ms,
        percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95_latency_ms,
        MAX(latency_ms) AS max_latency_ms,
        AVG(confidence) AS avg_confidence,
        SUM(CASE WHEN confidence < %(low_confidence_threshold)s THEN 1 ELSE 0 END)
            AS low_confidence_count,
        MAX(created_at) AS latest_log_at
    FROM recent_logs;
    """

    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                metrics_sql,
                {
                    "limit": limit,
                    "low_confidence_threshold": DEFAULT_LOW_CONFIDENCE_THRESHOLD,
                },
            )
            row = cursor.fetchone()

    return {
        "total_logs": int(row["total_logs"] or 0),
        "avg_latency_ms": round(float(row["avg_latency_ms"]), 2)
        if row["avg_latency_ms"] is not None
        else None,
        "p95_latency_ms": round(float(row["p95_latency_ms"]), 2)
        if row["p95_latency_ms"] is not None
        else None,
        "max_latency_ms": round(float(row["max_latency_ms"]), 2)
        if row["max_latency_ms"] is not None
        else None,
        "avg_confidence": round(float(row["avg_confidence"]), 4)
        if row["avg_confidence"] is not None
        else None,
        "low_confidence_count": int(row["low_confidence_count"] or 0),
        "latest_log_at": row["latest_log_at"],
    }


def build_current_alerts(
    limit: int = 100,
    latency_p95_threshold_ms: float = DEFAULT_LATENCY_P95_THRESHOLD_MS,
    avg_confidence_threshold: float = DEFAULT_AVG_CONFIDENCE_THRESHOLD,
    low_confidence_threshold: float = DEFAULT_LOW_CONFIDENCE_THRESHOLD,
    drift_alpha: float = 0.05,
    drift_min_samples: int = 20,
) -> dict:
    metrics = fetch_recent_alert_metrics(limit=limit)

    drift_report = build_ks_drift_report(
        profile="all",
        limit=limit,
        alpha=drift_alpha,
        min_samples=drift_min_samples,
    )

    alerts: list[dict] = []

    if metrics["total_logs"] == 0:
        alerts.append(
            {
                "name": "no_inference_logs",
                "severity": "info",
                "message": "No inference logs have been collected yet.",
                "metric_value": 0,
                "threshold": None,
            }
        )

    p95_latency = metrics["p95_latency_ms"]
    if p95_latency is not None and p95_latency > latency_p95_threshold_ms:
        alerts.append(
            {
                "name": "high_p95_latency",
                "severity": "warning",
                "message": "Recent p95 inference latency is above the configured threshold.",
                "metric_value": p95_latency,
                "threshold": latency_p95_threshold_ms,
            }
        )

    avg_confidence = metrics["avg_confidence"]
    if avg_confidence is not None and avg_confidence < avg_confidence_threshold:
        alerts.append(
            {
                "name": "low_average_confidence",
                "severity": "warning",
                "message": "Recent average model confidence is below the configured threshold.",
                "metric_value": avg_confidence,
                "threshold": avg_confidence_threshold,
            }
        )

    if metrics["low_confidence_count"] > 0:
        alerts.append(
            {
                "name": "low_confidence_events",
                "severity": "info",
                "message": "Some recent inference events have very low confidence.",
                "metric_value": metrics["low_confidence_count"],
                "threshold": low_confidence_threshold,
            }
        )

    if drift_report["drift_detected"]:
        drifted_features = [
            feature["feature_name"]
            for feature in drift_report["features"]
            if feature["drift_detected"]
        ]

        alerts.append(
            {
                "name": "data_drift_detected",
                "severity": "critical",
                "message": "Kolmogorov-Smirnov test detected feature distribution drift.",
                "metric_value": len(drifted_features),
                "threshold": drift_alpha,
            }
        )

    status = "ok"
    if any(alert["severity"] == "critical" for alert in alerts):
        status = "critical"
    elif any(alert["severity"] == "warning" for alert in alerts):
        status = "warning"
    elif alerts:
        status = "info"

    return {
        "status": status,
        "alert_count": len(alerts),
        "critical_count": sum(1 for alert in alerts if alert["severity"] == "critical"),
        "warning_count": sum(1 for alert in alerts if alert["severity"] == "warning"),
        "info_count": sum(1 for alert in alerts if alert["severity"] == "info"),
        "evaluation_window": {
            "recent_log_limit": limit,
            "latest_log_at": metrics["latest_log_at"],
        },
        "thresholds": {
            "latency_p95_threshold_ms": latency_p95_threshold_ms,
            "avg_confidence_threshold": avg_confidence_threshold,
            "low_confidence_threshold": low_confidence_threshold,
            "drift_alpha": drift_alpha,
            "drift_min_samples": drift_min_samples,
        },
        "metrics": metrics,
        "alerts": alerts,
    }
