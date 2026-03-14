from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ..db.models import MemoryEmbedding, MemoryItem


def create_memory_item(
    db: Session,
    *,
    memory_type: str,
    content: str,
    source_trip_plan_id: uuid.UUID | None = None,
    metadata: dict[str, Any] | None = None,
    weight: float = 1.0,
) -> MemoryItem:
    memory_item = MemoryItem(
        memory_type=memory_type,
        content=content,
        source_trip_plan_id=source_trip_plan_id,
        meta=metadata or {},
        weight=Decimal(str(weight)),
    )
    db.add(memory_item)
    db.flush()
    return memory_item


def get_latest_memory_by_signal(
    db: Session,
    *,
    signal: str,
    memory_type: str | None = None,
) -> MemoryItem | None:
    stmt = (
        select(MemoryItem)
        .where(MemoryItem.meta["source"].as_string() == "edit")
        .where(MemoryItem.meta["signal"].as_string() == signal)
        .order_by(MemoryItem.created_at.desc())
        .limit(1)
    )
    if memory_type:
        stmt = stmt.where(MemoryItem.memory_type == memory_type)
    return db.scalar(stmt)


def update_memory_item(
    db: Session,
    *,
    memory_item: MemoryItem,
    content: str,
    metadata: dict[str, Any] | None = None,
    source_trip_plan_id: uuid.UUID | None = None,
    weight: float | None = None,
) -> MemoryItem:
    memory_item.content = content
    if metadata is not None:
        memory_item.meta = metadata
    memory_item.source_trip_plan_id = source_trip_plan_id
    if weight is not None:
        memory_item.weight = Decimal(str(weight))
    memory_item.last_used_at = datetime.utcnow()
    db.flush()
    return memory_item


def upsert_memory_embedding(
    db: Session,
    *,
    memory_item_id: uuid.UUID,
    embedding: list[float],
) -> MemoryEmbedding:
    memory_embedding = db.get(MemoryEmbedding, memory_item_id)
    if memory_embedding is None:
        memory_embedding = MemoryEmbedding(memory_item_id=memory_item_id, embedding=embedding)
        db.add(memory_embedding)
    else:
        memory_embedding.embedding = embedding
    db.flush()
    return memory_embedding


def search_memories_by_embedding(
    db: Session,
    *,
    query_embedding: list[float],
    limit: int = 5,
    memory_types: list[str] | None = None,
) -> list[MemoryItem]:
    stmt = (
        select(MemoryItem)
        .join(MemoryEmbedding, MemoryEmbedding.memory_item_id == MemoryItem.id)
        .options(joinedload(MemoryItem.embedding))
        .order_by(MemoryEmbedding.embedding.cosine_distance(query_embedding))
        .limit(limit)
    )
    if memory_types:
        stmt = stmt.where(MemoryItem.memory_type.in_(memory_types))
    return list(db.scalars(stmt))


def list_recent_memories(
    db: Session,
    *,
    limit: int = 5,
    memory_types: list[str] | None = None,
) -> list[MemoryItem]:
    stmt = (
        select(MemoryItem)
        .options(joinedload(MemoryItem.embedding))
        .order_by(MemoryItem.created_at.desc())
        .limit(limit)
    )
    if memory_types:
        stmt = stmt.where(MemoryItem.memory_type.in_(memory_types))
    return list(db.scalars(stmt))


def mark_memories_used(db: Session, memories: list[MemoryItem]) -> None:
    if not memories:
        return
    now = datetime.utcnow()
    for memory in memories:
        memory.last_used_at = now
    db.flush()
