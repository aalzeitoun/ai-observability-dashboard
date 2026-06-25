import os
from contextlib import contextmanager
from typing import Generator

import psycopg
from psycopg.rows import dict_row


def get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise RuntimeError("DATABASE_URL environment variable is not set.")

    return database_url


@contextmanager
def get_db_connection() -> Generator[psycopg.Connection, None, None]:
    connection = psycopg.connect(
        get_database_url(),
        row_factory=dict_row,
    )

    try:
        yield connection
    finally:
        connection.close()


def init_db() -> None:
    migration_sql = """
    CREATE TABLE IF NOT EXISTS inference_logs (
        id SERIAL PRIMARY KEY,
        request_id TEXT NOT NULL UNIQUE,
        model_name TEXT NOT NULL,
        features JSONB NOT NULL,
        prediction INTEGER NOT NULL,
        confidence DOUBLE PRECISION NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
        latency_ms DOUBLE PRECISION NOT NULL CHECK (latency_ms >= 0),
        profile TEXT NOT NULL DEFAULT 'manual',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT inference_logs_profile_check CHECK (profile IN ('manual', 'normal', 'drift'))
    );

    ALTER TABLE inference_logs
    ADD COLUMN IF NOT EXISTS profile TEXT NOT NULL DEFAULT 'manual';

    UPDATE inference_logs
    SET profile = 'manual'
    WHERE profile IS NULL;

    DO $$
    BEGIN
        ALTER TABLE inference_logs
        ADD CONSTRAINT inference_logs_profile_check
        CHECK (profile IN ('manual', 'normal', 'drift'));
    EXCEPTION
        WHEN duplicate_object THEN NULL;
    END $$;

    CREATE INDEX IF NOT EXISTS idx_inference_logs_created_at
    ON inference_logs (created_at DESC);

    CREATE INDEX IF NOT EXISTS idx_inference_logs_model_name
    ON inference_logs (model_name);

    CREATE INDEX IF NOT EXISTS idx_inference_logs_profile
    ON inference_logs (profile);

    CREATE TABLE IF NOT EXISTS reference_feature_values (
        id SERIAL PRIMARY KEY,
        dataset_name TEXT NOT NULL,
        row_index INTEGER NOT NULL,
        feature_name TEXT NOT NULL,
        feature_value DOUBLE PRECISION NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT reference_feature_values_unique
        UNIQUE (dataset_name, row_index, feature_name)
    );

    CREATE INDEX IF NOT EXISTS idx_reference_feature_values_dataset
    ON reference_feature_values (dataset_name);

    CREATE INDEX IF NOT EXISTS idx_reference_feature_values_feature
    ON reference_feature_values (feature_name);
    """

    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(migration_sql)

        connection.commit()
