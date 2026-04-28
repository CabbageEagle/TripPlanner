"""Tool wrapper for real weather lookup."""

from __future__ import annotations

from typing import Any

from langchain_core.tools import tool
from pydantic import BaseModel, Field, field_validator

from ...services.amap_service import get_amap_service


class QueryWeatherInput(BaseModel):
    """Schema for query_weather_tool."""

    city: str = Field(..., description="Target city")
    date_range: list[str] = Field(..., description="Trip date range as [start_date, end_date]")

    @field_validator("city")
    @classmethod
    def validate_city(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("city must not be empty")
        return value

    @field_validator("date_range")
    @classmethod
    def validate_date_range(cls, value: list[str]) -> list[str]:
        if len(value) != 2:
            raise ValueError("date_range must contain [start_date, end_date]")
        normalized = [str(item).strip() for item in value]
        if not all(normalized):
            raise ValueError("date_range values must not be empty")
        return normalized


def _model_to_dict(item: Any) -> dict[str, Any]:
    if hasattr(item, "model_dump"):
        return item.model_dump(mode="json")
    if isinstance(item, dict):
        return item
    return dict(item)


def _render_weather_text(city: str, items: list[dict[str, Any]], warning: str | None) -> str:
    if not items:
        base = f"No real weather entries were returned for {city}."
        return f"{base} Warning: {warning}" if warning else base

    lines = [f"Found {len(items)} real weather entries for {city}."]
    for index, item in enumerate(items, start=1):
        lines.append(
            f"{index}. {item.get('date', 'date unknown')} | "
            f"day: {item.get('day_weather', '')} {item.get('day_temp', '')} | "
            f"night: {item.get('night_weather', '')} {item.get('night_temp', '')} | "
            f"wind: {item.get('wind_direction', '')} {item.get('wind_power', '')}"
        )
    if warning:
        lines.append(f"Warning: {warning}")
    return "\n".join(lines)


@tool("query_weather_tool", args_schema=QueryWeatherInput)
def query_weather_tool(city: str, date_range: list[str]) -> dict[str, Any]:
    """Use this tool to query real weather information for the target city. Always use real service data; do not invent or estimate weather when the service returns no items."""

    warning = None
    try:
        service = get_amap_service()
        items = [_model_to_dict(item) for item in service.get_weather(city)]
    except Exception as exc:
        items = []
        warning = f"AMap weather lookup failed: {exc}"

    if not items and warning is None:
        warning = "AMap returned no weather data."

    return {
        "text": _render_weather_text(city, items, warning),
        "items": items,
        "warning": warning,
        "meta": {
            "date_range": date_range,
            "source": "amap",
        },
    }
