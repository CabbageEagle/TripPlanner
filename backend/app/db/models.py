from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import Date, DateTime, ForeignKey, Index, Numeric, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class TripPlanRecord(Base):
    __tablename__ = "trip_plans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    city: Mapped[str] = mapped_column(Text, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    travel_days: Mapped[int] = mapped_column(nullable=False)
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    current_plan_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="generated", server_default="generated")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    versions: Mapped[list["TripPlanVersion"]] = relationship(
        back_populates="trip_plan",
        cascade="all, delete-orphan",
        order_by="desc(TripPlanVersion.version_no)",
    )
    memory_items: Mapped[list["MemoryItem"]] = relationship(back_populates="source_trip_plan")

    __table_args__ = (Index("idx_trip_plans_created_at", "created_at"),)


class TripPlanVersion(Base):
    __tablename__ = "trip_plan_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trip_plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("trip_plans.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_no: Mapped[int] = mapped_column(nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    plan_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    trip_plan: Mapped["TripPlanRecord"] = relationship(back_populates="versions")

    __table_args__ = (
        UniqueConstraint("trip_plan_id", "version_no", name="uq_trip_plan_versions_trip_plan_id_version_no"),
        Index("idx_trip_plan_versions_trip_plan_id", "trip_plan_id", "version_no"),
    )


class MemoryItem(Base):
    __tablename__ = "memory_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    memory_type: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_trip_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("trip_plans.id", ondelete="SET NULL"),
        nullable=True,
    )
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False, default=dict, server_default="{}")
    weight: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False, default=1.0, server_default="1.0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    source_trip_plan: Mapped["TripPlanRecord | None"] = relationship(back_populates="memory_items")
    embedding: Mapped["MemoryEmbedding | None"] = relationship(
        back_populates="memory_item",
        cascade="all, delete-orphan",
        uselist=False,
    )

    __table_args__ = (
        Index("idx_memory_items_type_created_at", "memory_type", "created_at"),
        Index("idx_memory_items_source_trip_plan_id", "source_trip_plan_id"),
    )


class MemoryEmbedding(Base):
    __tablename__ = "memory_embeddings"

    memory_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("memory_items.id", ondelete="CASCADE"),
        primary_key=True,
    )
    embedding: Mapped[list[float]] = mapped_column(Vector(1536), nullable=False)

    memory_item: Mapped["MemoryItem"] = relationship(back_populates="embedding")
