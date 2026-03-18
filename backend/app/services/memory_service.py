from __future__ import annotations

import hashlib
import math
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from langchain_openai import OpenAIEmbeddings
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db.models import MemoryItem
from ..models.schemas import Attraction, TripPlan, TripRequest
from ..repositories.memory_repository import (
    create_memory_item,
    get_latest_memory_by_signal,
    list_recent_memories,
    mark_memories_used,
    search_memories_by_embedding,
    update_memory_item,
    upsert_memory_embedding,
)

MEMORY_RETRIEVAL_TYPES = ["preference", "dislike", "habit", "constraint", "summary"]
EMBEDDING_DIMENSIONS = 1536
@dataclass
class MemoryDraft:
    memory_type: str
    content: str
    metadata: dict[str, Any]
    weight: float = 1.0

def build_request_query_text(request: TripRequest) -> str:
    return "\n".join(
        [
            f"城市: {request.city}",
            f"日期: {request.start_date} - {request.end_date}",
            f"出行天数: {request.travel_days}",
            f"交通方式: {request.transportation}",
            f"住宿偏好: {request.accommodation}",
            f"偏好标签: {', '.join(request.preferences) if request.preferences else '未填写'}",
            f"额外要求: {request.free_text_input or '无'}",
            f"总预算: {request.max_budget or '未填写'}",
            f"每日预算: {request.budget_per_day or '未填写'}",
            f"每日开始时间: {request.daily_start_time or '未填写'}",
            f"每日结束时间: {request.daily_end_time or '未填写'}",
            f"每日最多景点数: {request.max_attractions_per_day or '未填写'}",
        ]
    )


def extract_memories_from_request(request: TripRequest) -> list[MemoryDraft]:
    memories: list[MemoryDraft] = []

    if request.preferences:
        preferences_text = "、".join(request.preferences)
        memories.append(
            MemoryDraft(
                memory_type="preference",
                content=f"用户偏好 {preferences_text} 类型的旅行体验。",
                metadata={"source": "request", "preferences": request.preferences},
                weight=0.9,
            )
        )

    if request.free_text_input:
        cleaned_text = request.free_text_input.strip()
        memories.append(
            MemoryDraft(
                memory_type="constraint",
                content=f"用户额外要求：{cleaned_text}",
                metadata={"source": "request", "field": "free_text_input"},
                weight=1.0,
            )
        )

    if request.max_attractions_per_day:
        memories.append(
            MemoryDraft(
                memory_type="habit",
                content=f"用户通常希望每天最多安排 {request.max_attractions_per_day} 个景点。",
                metadata={"source": "request", "field": "max_attractions_per_day"},
                weight=0.85,
            )
        )

    if request.max_budget or request.budget_per_day:
        budget_desc = []
        if request.max_budget:
            budget_desc.append(f"总预算约 {request.max_budget} 元")
        if request.budget_per_day:
            budget_desc.append(f"每日预算约 {request.budget_per_day} 元")
        memories.append(
            MemoryDraft(
                memory_type="constraint",
                content=f"用户预算偏好：{'，'.join(budget_desc)}。",
                metadata={"source": "request", "field": "budget"},
                weight=0.95,
            )
        )

    if request.transportation:
        memories.append(
            MemoryDraft(
                memory_type="habit",
                content=f"用户通常倾向使用 {request.transportation} 作为主要交通方式。",
                metadata={"source": "request", "field": "transportation"},
                weight=0.75,
            )
        )

    if request.accommodation:
        memories.append(
            MemoryDraft(
                memory_type="habit",
                content=f"用户住宿偏好接近 {request.accommodation}。",
                metadata={"source": "request", "field": "accommodation"},
                weight=0.75,
            )
        )

    return _deduplicate_memories(memories)


def extract_memories_from_edit(
    previous_plan: TripPlan,
    updated_plan: TripPlan,
    *,
    note: str | None = None,
) -> list[MemoryDraft]:
    memories: list[MemoryDraft] = []

    previous_count = sum(len(day.attractions) for day in previous_plan.days)
    updated_count = sum(len(day.attractions) for day in updated_plan.days)
    previous_duration = sum(day.total_duration or 0 for day in previous_plan.days)
    updated_duration = sum(day.total_duration or 0 for day in updated_plan.days)

    if updated_count < previous_count or (previous_duration and updated_duration and updated_duration < previous_duration * 0.85):
        memories.append(
            MemoryDraft(
                memory_type="habit",
                content="用户会主动减少景点或压缩时长，偏好更轻松、不过度赶路的节奏。",
                metadata={
                    "source": "edit",
                    "signal": "pace_relaxed",
                    "previous_attractions": previous_count,
                    "updated_attractions": updated_count,
                    "previous_duration": previous_duration,
                    "updated_duration": updated_duration,
                },
                weight=0.95,
            )
        )
    elif updated_count > previous_count:
        memories.append(
            MemoryDraft(
                memory_type="preference",
                content="用户愿意增加景点数量，能够接受更充实的行程安排。",
                metadata={"source": "edit", "signal": "pace_dense", "previous_attractions": previous_count, "updated_attractions": updated_count},
                weight=0.75,
            )
        )

    attraction_preference_memory = _build_attraction_preference_memory(previous_plan, updated_plan)
    if attraction_preference_memory:
        memories.append(attraction_preference_memory)

    accommodation_memory = _build_accommodation_preference_memory(previous_plan, updated_plan)
    if accommodation_memory:
        memories.append(accommodation_memory)

    if previous_plan.overall_suggestions != updated_plan.overall_suggestions and not memories:
        memories.append(
            MemoryDraft(
                memory_type="summary",
                content=f"用户编辑后的整体行程倾向：{updated_plan.overall_suggestions}",
                metadata={"source": "edit", "field": "overall_suggestions"},
                weight=0.7,
            )
        )

    if note and not memories:
        memories.append(
            MemoryDraft(
                memory_type="summary",
                content=f"用户编辑备注：{note}",
                metadata={"source": "edit", "field": "note"},
                weight=0.6,
            )
        )

    return _select_strong_memories(memories, limit=3)


def persist_memories(
    db: Session,
    *,
    memories: list[MemoryDraft],
    source_trip_plan_id: uuid.UUID | None = None,
) -> list[MemoryItem]:
    stored_memories: list[MemoryItem] = []
    for memory in memories:
        item = _store_memory(
            db,
            memory=memory,
            source_trip_plan_id=source_trip_plan_id,
        )
        embedding = embed_text(memory.content)
        upsert_memory_embedding(db, memory_item_id=item.id, embedding=embedding)
        stored_memories.append(item)
    return stored_memories


def retrieve_relevant_memories(db: Session, *, request: TripRequest, limit: int = 5) -> list[MemoryItem]:
    query_embedding = embed_text(build_request_query_text(request))
    memories = search_memories_by_embedding(
        db,
        query_embedding=query_embedding,
        limit=limit,
        memory_types=MEMORY_RETRIEVAL_TYPES,
    )
    if not memories:
        memories = list_recent_memories(db, limit=limit, memory_types=MEMORY_RETRIEVAL_TYPES)
    mark_memories_used(db, memories)
    return memories


def summarize_preferences(memories: list[MemoryItem]) -> str:
    if not memories:
        return ""

    lines: list[str] = []
    seen: set[str] = set()
    for memory in memories:
        normalized = memory.content.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        lines.append(f"- {normalized}")
        if len(lines) >= 4:
            break
    return "\n".join(lines)


def embed_text(text: str) -> list[float]:
    settings = get_settings()
    api_key = settings.openai_api_key
    if api_key:
        try:
            embeddings = OpenAIEmbeddings(
                model=settings.openai_embedding_model,
                api_key=api_key,
                base_url=settings.openai_base_url,
            )
            return embeddings.embed_query(text)
        except Exception:
            return _hash_embedding(text)
    return _hash_embedding(text)


def _deduplicate_memories(memories: list[MemoryDraft]) -> list[MemoryDraft]:
    unique: list[MemoryDraft] = []
    seen: set[tuple[str, str]] = set()
    for memory in memories:
        key = (memory.memory_type, memory.content.strip())
        if key in seen or not memory.content.strip():
            continue
        seen.add(key)
        unique.append(memory)
    return unique


def _select_strong_memories(memories: list[MemoryDraft], *, limit: int) -> list[MemoryDraft]:
    deduplicated = _deduplicate_memories(memories)
    deduplicated.sort(key=lambda item: item.weight, reverse=True)
    return deduplicated[:limit]


def _store_memory(
    db: Session,
    *,
    memory: MemoryDraft,
    source_trip_plan_id: uuid.UUID | None,
) -> MemoryItem:
    signal = memory.metadata.get("signal")
    source = memory.metadata.get("source")
    if source == "edit" and signal:
        existing_memory = get_latest_memory_by_signal(
            db,
            signal=signal,
            memory_type=memory.memory_type,
        )
        if existing_memory is not None:
            return update_memory_item(
                db,
                memory_item=existing_memory,
                content=memory.content,
                metadata=memory.metadata,
                source_trip_plan_id=source_trip_plan_id,
                weight=memory.weight,
            )

    return create_memory_item(
        db,
        memory_type=memory.memory_type,
        content=memory.content,
        source_trip_plan_id=source_trip_plan_id,
        metadata=memory.metadata,
        weight=memory.weight,
    )


def _build_attraction_preference_memory(previous_plan: TripPlan, updated_plan: TripPlan) -> MemoryDraft | None:
    previous_tags = _count_attraction_tags(previous_plan)
    updated_tags = _count_attraction_tags(updated_plan)

    nature_delta = updated_tags["nature"] - previous_tags["nature"]
    culture_delta = updated_tags["culture"] - previous_tags["culture"]

    if nature_delta >= 1 and culture_delta <= 0:
        return MemoryDraft(
            memory_type="preference",
            content="用户编辑后更偏好自然风光类景点，而不是密集的人文参观点。",
            metadata={"source": "edit", "signal": "prefer_nature", "previous_tags": previous_tags, "updated_tags": updated_tags},
            weight=0.9,
        )

    if culture_delta >= 1 and nature_delta <= 0:
        return MemoryDraft(
            memory_type="preference",
            content="用户编辑后更偏好历史文化类景点，愿意为人文体验留出时间。",
            metadata={"source": "edit", "signal": "prefer_culture", "previous_tags": previous_tags, "updated_tags": updated_tags},
            weight=0.9,
        )

    if previous_tags["culture"] > updated_tags["culture"] and updated_tags["nature"] >= previous_tags["nature"]:
        return MemoryDraft(
            memory_type="dislike",
            content="用户会主动减少历史文化类景点，说明不喜欢过于密集的文化参观安排。",
            metadata={"source": "edit", "signal": "avoid_dense_culture", "previous_tags": previous_tags, "updated_tags": updated_tags},
            weight=0.88,
        )

    return None


def _build_accommodation_preference_memory(previous_plan: TripPlan, updated_plan: TripPlan) -> MemoryDraft | None:
    previous_preference = _extract_primary_accommodation(previous_plan)
    updated_preference = _extract_primary_accommodation(updated_plan)

    if not previous_preference or not updated_preference or previous_preference == updated_preference:
        return None

    return MemoryDraft(
        memory_type="habit",
        content=f"用户最终更偏好 {updated_preference} 类型的住宿，而不是 {previous_preference}。",
        metadata={
            "source": "edit",
            "signal": "accommodation_shift",
            "previous_accommodation": previous_preference,
            "updated_accommodation": updated_preference,
        },
        weight=0.82,
    )


def _count_attraction_tags(plan: TripPlan) -> dict[str, int]:
    counts = {"nature": 0, "culture": 0}
    for day in plan.days:
        for attraction in day.attractions:
            tag = _classify_attraction(attraction)
            if tag:
                counts[tag] += 1
    return counts


def _classify_attraction(attraction: Attraction) -> str | None:
    text = " ".join(filter(None, [attraction.name, attraction.description, attraction.category or ""]))

    nature_keywords = ["自然", "公园", "风景", "山", "湖", "海", "森林", "湿地", "花园", "植物园", "动物园"]
    culture_keywords = ["历史", "文化", "博物馆", "故宫", "古镇", "遗址", "寺", "展览", "艺术馆", "名人故居", "古建筑"]

    if any(keyword in text for keyword in nature_keywords):
        return "nature"
    if any(keyword in text for keyword in culture_keywords):
        return "culture"
    return None


def _extract_primary_accommodation(plan: TripPlan) -> str | None:
    for day in plan.days:
        hotel_type = day.hotel.type if day.hotel and day.hotel.type else None
        if hotel_type:
            return hotel_type
        if day.accommodation:
            return day.accommodation
    return None


def _hash_embedding(text: str, dimensions: int = EMBEDDING_DIMENSIONS) -> list[float]:
    vector = [0.0] * dimensions
    tokens = re.findall(r"\w+|[\u4e00-\u9fff]", text.lower())
    if not tokens:
        return vector

    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        magnitude = 1.0 + (digest[5] / 255.0)
        vector[bucket] += sign * magnitude

    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]
