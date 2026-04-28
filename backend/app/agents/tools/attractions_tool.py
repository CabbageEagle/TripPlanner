"""Tool wrapper for real attraction candidate lookup."""

from __future__ import annotations

from typing import Any

from langchain_core.tools import tool
from pydantic import BaseModel, Field, field_validator

from ...services.amap_service import get_amap_service


class SearchAttractionsInput(BaseModel):
    """Schema for search_attractions_tool."""

    city: str = Field(..., description="Target city")
    keywords: list[str] = Field(default_factory=list, description="Preference keywords for attraction search")

    @field_validator("city")
    @classmethod
    def validate_city(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("city must not be empty")
        return value

    @field_validator("keywords")
    @classmethod
    def normalize_keywords(cls, value: list[str]) -> list[str]:
        return [str(item).strip() for item in value if str(item).strip()]


def _model_to_dict(item: Any) -> dict[str, Any]:
    if hasattr(item, "model_dump"):
        return item.model_dump(mode="json")
    if isinstance(item, dict):
        return item
    return dict(item)


def _normalize_attraction_item(item: dict[str, Any], city: str) -> dict[str, Any] | None:
    name = str(item.get("name") or "").strip()
    if not name or not item.get("location"):
        return None
    return {
        "name": name,
        "address": item.get("address", ""),
        "location": item.get("location"),
        "visit_duration": 120,
        "description": f"{name}, suitable as an attraction candidate for a {city} itinerary.",
        "category": item.get("type", "attraction"),
        "ticket_price": 0,
        "poi_id": item.get("id", ""),
    }


def _render_attractions_text(city: str, items: list[dict[str, Any]], warning: str | None) -> str:
    if not items:
        base = f"No real attraction candidates were returned for {city}."
        return f"{base} Warning: {warning}" if warning else base

    lines = [f"Found {len(items)} real attraction candidates for {city}."]
    for index, item in enumerate(items, start=1):
        lines.append(
            f"{index}. {item.get('name', 'unknown')} | {item.get('category', 'attraction')} | "
            f"{item.get('address', '')}"
        )
    if warning:
        lines.append(f"Warning: {warning}")
    return "\n".join(lines)


@tool("search_attractions_tool", args_schema=SearchAttractionsInput)
def search_attractions_tool(city: str, keywords: list[str] | None = None) -> dict[str, Any]:
    """Use this tool to query real attraction candidates for the target city. Use real service data only; do not invent attractions when the service returns no items."""

    keyword = " ".join(keywords or []) or "热门景点"
    warning = None
    try:
        service = get_amap_service()
        pois = service.search_poi(keyword, city, citylimit=True)
        items = [
            normalized
            for normalized in (
                _normalize_attraction_item(_model_to_dict(item), city)
                for item in pois
            )
            if normalized is not None
        ][:10]
    except Exception as exc:
        items = []
        warning = f"AMap attraction search failed: {exc}"

    if not items and warning is None:
        warning = "AMap returned no attraction candidates."

    return {
        "text": _render_attractions_text(city, items, warning),
        "items": items,
        "warning": warning,
        "meta": {
            "source": "amap",
            "keywords": keywords or [],
        },
    }
