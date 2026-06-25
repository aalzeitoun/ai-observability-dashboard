from typing import Literal

from scipy.stats import ks_2samp

from app.db import get_db_connection
from app.model import model_simulator
from app.reference_data import REFERENCE_DATASET_NAME, fetch_reference_values


ProductionProfile = Literal["all", "manual", "normal", "drift"]


def mean_or_none(values: list[float]) -> float | None:
    if not values:
        return None

    return round(sum(values) / len(values), 4)


def fetch_production_feature_values(
    feature_name: str,
    limit: int,
    profile: ProductionProfile,
) -> list[float]:
    where_clauses = ["features ? %(feature_name)s"]
    params = {
        "feature_name": feature_name,
        "limit": limit,
    }

    if profile != "all":
        where_clauses.append("profile = %(profile)s")
        params["profile"] = profile

    values_sql = f"""
    SELECT
        (features ->> %(feature_name)s)::DOUBLE PRECISION AS feature_value
    FROM inference_logs
    WHERE {" AND ".join(where_clauses)}
    ORDER BY created_at DESC
    LIMIT %(limit)s;
    """

    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(values_sql, params)
            rows = cursor.fetchall()

    return [float(row["feature_value"]) for row in rows]


def build_ks_drift_report(
    profile: ProductionProfile = "all",
    limit: int = 100,
    alpha: float = 0.05,
    min_samples: int = 20,
) -> dict:
    feature_results = []
    overall_drift_detected = False

    for feature_name in model_simulator.feature_names:
        reference_values = fetch_reference_values(feature_name)
        production_values = fetch_production_feature_values(
            feature_name=feature_name,
            limit=limit,
            profile=profile,
        )

        insufficient_data = len(production_values) < min_samples

        if insufficient_data:
            feature_result = {
                "feature_name": feature_name,
                "reference_sample_count": len(reference_values),
                "production_sample_count": len(production_values),
                "reference_mean": mean_or_none(reference_values),
                "production_mean": mean_or_none(production_values),
                "ks_statistic": None,
                "p_value": None,
                "drift_detected": False,
                "insufficient_data": True,
            }
        else:
            ks_result = ks_2samp(
                reference_values,
                production_values,
                alternative="two-sided",
                method="auto",
            )

            ks_statistic = round(float(ks_result.statistic), 6)
            p_value = round(float(ks_result.pvalue), 6)
            drift_detected = p_value < alpha
            overall_drift_detected = overall_drift_detected or drift_detected

            feature_result = {
                "feature_name": feature_name,
                "reference_sample_count": len(reference_values),
                "production_sample_count": len(production_values),
                "reference_mean": mean_or_none(reference_values),
                "production_mean": mean_or_none(production_values),
                "ks_statistic": ks_statistic,
                "p_value": p_value,
                "drift_detected": drift_detected,
                "insufficient_data": False,
            }

        feature_results.append(feature_result)

    return {
        "dataset_name": REFERENCE_DATASET_NAME,
        "profile": profile,
        "production_limit": limit,
        "alpha": alpha,
        "min_samples": min_samples,
        "drift_detected": overall_drift_detected,
        "features": feature_results,
    }
