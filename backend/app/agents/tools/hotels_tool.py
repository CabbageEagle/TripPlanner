"""Tool wrapper for real hotel candidate lookup."""

from __future__ import annotations

from typing import Any

from langchain_core.tools import tool
from pydantic import BaseModel, Field, field_validator

from ...services.amap_service import get_amap_service


class SearchHotelsInput(BaseModel):
    """Schema for search_hotels_tool."""

    city: str = Field(..., description="Target city")
    accommodation: str | None = Field(default=None, description="Accommodation preference")

    @field_validator("city")
    @classmethod
    def validate_city(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("city must not be empty")
        return value


def _model_to_dict(item: Any) -> dict[str, Any]:
    if hasattr(item, "model_dump"):
        return item.model_dump(mode="json")
    if isinstance(item, dict):
        return item
    return dict(item)


def _normalize_hotel_item(item: dict[str, Any], accommodation: str | None) -> dict[str, Any] | None:
    name = str(item.get("name") or "").strip()
    if not name:
        return None
    return {
        "name": name,
        "address": item.get("address", ""),
        "location": item.get("location"),
        "price_range": item.get("price_range", ""),
        "rating": item.get("rating", ""),
        "distance": item.get("distance", ""),
        "type": item.get("type") or accommodation or "hotel",
        "estimated_cost": item.get("estimated_cost", 0),
        "poi_id": item.get("id", ""),
    }


def _render_hotels_text(city: str, items: list[dict[str, Any]], warning: str | None) -> str:
    if not items:
        base = f"No real hotel candidates were returned for {city}."
        return f"{base} Warning: {warning}" if warning else base

    lines = [f"Found {len(items)} real hotel candidates for {city}."]
    for index, item in enumerate(items, start=1):
        lines.append(
            f"{index}. {item.get('name', 'unknown')} | {item.get('type', 'hotel')} | "
            f"{item.get('address', '')} | rating: {item.get('rating', '')}"
        )
    if warning:
        lines.append(f"Warning: {warning}")
    return "\n".join(lines)


@tool("search_hotels_tool", args_schema=SearchHotelsInput)
def search_hotels_tool(city: str, accommodation: str | None = None) -> dict[str, Any]:
    """Use this tool to query real hotel candidates for the target city. Use real service data only; do not invent hotels when the service returns no items."""

    warning = None
    keyword = accommodation or "hotel"
    try:
        service = get_amap_service()
        pois = service.search_poi(keyword, city, citylimit=True)
        items = [
            normalized
            for normalized in (
                _normalize_hotel_item(_model_to_dict(item), accommodation)
                for item in pois
            )
            if normalized is not None and normalized.get("location")
        ][:5]
    except Exception as exc:
        items = []
        warning = f"AMap hotel search failed: {exc}"

    if not items and warning is None:
        warning = "AMap returned no hotel candidates."

    return {
        "text": _render_hotels_text(city, items, warning),
        "items": items,
        "warning": warning,
        "meta": {
            "source": "amap",
            "accommodation": accommodation,
        },
    }
