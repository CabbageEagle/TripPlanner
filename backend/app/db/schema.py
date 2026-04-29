"""Runtime database schema checks for local development."""

from __future__ import annotations

from sqlalchemy import text

from .models import Base
from .session import engine


def ensure_runtime_schema() -> None:
    """Create missing tables and patch small backward-compatible schema gaps."""
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        Base.metadata.create_all(bind=conn)
        conn.execute(
            text(
                """
                ALTER TABLE memory_items
                ADD COLUMN IF NOT EXISTS source_trip_plan_id UUID NULL
                """
            )
        )
        conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1
                        FROM pg_constraint
                        WHERE conname = 'fk_memory_items_source_trip_plan_id'
                    ) THEN
                        ALTER TABLE memory_items
                        ADD CONSTRAINT fk_memory_items_source_trip_plan_id
                        FOREIGN KEY (source_trip_plan_id)
                        REFERENCES trip_plans(id)
                        ON DELETE SET NULL;
                    END IF;
                END $$;
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS idx_memory_items_source_trip_plan_id
                ON memory_items (source_trip_plan_id)
                """
            )
        )
