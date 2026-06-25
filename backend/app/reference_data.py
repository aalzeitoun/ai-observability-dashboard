from app.db import get_db_connection
from app.model import model_simulator


REFERENCE_DATASET_NAME = "iris_training"


def seed_reference_data() -> None:
    count_sql = """
    SELECT COUNT(*) AS total
    FROM reference_feature_values
    WHERE dataset_name = %(dataset_name)s;
    """

    insert_sql = """
    INSERT INTO reference_feature_values (
        dataset_name,
        row_index,
        feature_name,
        feature_value
    )
    VALUES (
        %(dataset_name)s,
        %(row_index)s,
        %(feature_name)s,
        %(feature_value)s
    )
    ON CONFLICT (dataset_name, row_index, feature_name)
    DO NOTHING;
    """

    rows_to_insert: list[dict] = []

    for row_index, feature_values in enumerate(model_simulator.training_rows):
        for feature_name, feature_value in zip(
            model_simulator.feature_names,
            feature_values,
        ):
            rows_to_insert.append(
                {
                    "dataset_name": REFERENCE_DATASET_NAME,
                    "row_index": row_index,
                    "feature_name": feature_name,
                    "feature_value": float(feature_value),
                }
            )

    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(count_sql, {"dataset_name": REFERENCE_DATASET_NAME})
            row = cursor.fetchone()

            existing_count = int(row["total"] or 0)

            if existing_count == 0:
                cursor.executemany(insert_sql, rows_to_insert)

        connection.commit()


def fetch_reference_summary() -> dict:
    summary_sql = """
    SELECT
        dataset_name,
        feature_name,
        COUNT(*) AS sample_count,
        AVG(feature_value) AS mean_value,
        MIN(feature_value) AS min_value,
        MAX(feature_value) AS max_value
    FROM reference_feature_values
    GROUP BY dataset_name, feature_name
    ORDER BY feature_name ASC;
    """

    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(summary_sql)
            rows = cursor.fetchall()

    if not rows:
        return {
            "dataset_name": REFERENCE_DATASET_NAME,
            "total_features": 0,
            "total_values": 0,
            "features": [],
        }

    features = [
        {
            "feature_name": row["feature_name"],
            "sample_count": int(row["sample_count"]),
            "mean_value": round(float(row["mean_value"]), 4),
            "min_value": round(float(row["min_value"]), 4),
            "max_value": round(float(row["max_value"]), 4),
        }
        for row in rows
    ]

    return {
        "dataset_name": rows[0]["dataset_name"],
        "total_features": len(features),
        "total_values": sum(feature["sample_count"] for feature in features),
        "features": features,
    }


def fetch_reference_values(feature_name: str) -> list[float]:
    values_sql = """
    SELECT feature_value
    FROM reference_feature_values
    WHERE dataset_name = %(dataset_name)s
      AND feature_name = %(feature_name)s
    ORDER BY row_index ASC;
    """

    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                values_sql,
                {
                    "dataset_name": REFERENCE_DATASET_NAME,
                    "feature_name": feature_name,
                },
            )
            rows = cursor.fetchall()

    return [float(row["feature_value"]) for row in rows]
