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


def _build_hotel_search_keywords(city: str, accommodation: str | None) -> list[str]:
    """Convert lodging preference into concrete AMap POI search terms."""
    text = str(accommodation or "").strip()
    terms = ["酒店", "宾馆", "住宿", f"{city} 酒店"]
    if any(keyword in text for keyword in ("经济", "快捷", "便宜", "预算")):
        terms.extend(["快捷酒店", "连锁酒店", "经济酒店"])
    elif any(keyword in text for keyword in ("舒适", "商务", "中档")):
        terms.extend(["商务酒店", "中档酒店", "连锁酒店"])
    elif any(keyword in text for keyword in ("豪华", "高端", "五星", "度假")):
        terms.extend(["高端酒店", "五星级酒店", "度假酒店"])
    elif any(keyword in text for keyword in ("民宿", "客栈", "公寓")):
        terms = ["民宿", "客栈", "酒店式公寓", "住宿", f"{city} 民宿"]

    result: list[str] = []
    seen: set[str] = set()
    for term in terms:
        if not term or term in seen:
            continue
        seen.add(term)
        result.append(term)
        if len(result) >= 6:
            break
    return result


def _search_poi_with_warning(service: Any, keyword: str, city: str) -> tuple[list[Any], str | None]:
    if hasattr(service, "search_poi_with_raw"):
        return service.search_poi_with_raw(keyword, city, citylimit=True)
    return service.search_poi(keyword, city, citylimit=True), None


@tool("search_hotels_tool", args_schema=SearchHotelsInput)
def search_hotels_tool(city: str, accommodation: str | None = None) -> dict[str, Any]:
    """Use this tool to query real hotel candidates for the target city. Use real service data only; do not invent hotels when the service returns no items."""

    warning = None
    search_keywords = _build_hotel_search_keywords(city, accommodation)
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    warnings: list[str] = []
    try:
        service = get_amap_service()
        for keyword in search_keywords:
            pois, query_warning = _search_poi_with_warning(service, keyword, city)
            if query_warning:
                warnings.append(query_warning)
            for poi in pois:
                normalized = _normalize_hotel_item(_model_to_dict(poi), accommodation)
                if normalized is None:
                    continue
                dedupe_key = str(normalized.get("poi_id") or normalized.get("name") or "")
                if not dedupe_key or dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                items.append(normalized)
                if len(items) >= 5:
                    break
            if len(items) >= 5:
                break
    except Exception as exc:
        items = []
        warning = f"AMap hotel search failed: {exc}"

    if not items and warning is None:
        warning = " | ".join(warnings) if warnings else "AMap returned no hotel candidates."

    return {
        "text": _render_hotels_text(city, items, warning),
        "items": items,
        "warning": warning,
        "meta": {
            "source": "amap",
            "accommodation": accommodation,
            "search_keywords": search_keywords,
        },
    }
