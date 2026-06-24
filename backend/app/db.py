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
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS inference_logs (
        id SERIAL PRIMARY KEY,
        request_id TEXT NOT NULL UNIQUE,
        model_name TEXT NOT NULL,
        features JSONB NOT NULL,
        prediction INTEGER NOT NULL,
        confidence DOUBLE PRECISION NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
        latency_ms DOUBLE PRECISION NOT NULL CHECK (latency_ms >= 0),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS idx_inference_logs_created_at
    ON inference_logs (created_at DESC);

    CREATE INDEX IF NOT EXISTS idx_inference_logs_model_name
    ON inference_logs (model_name);
    """

    with get_db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(create_table_sql)

        connection.commit()
