"""Tool wrapper for optional local event discovery."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from langchain_core.tools import tool
from pydantic import BaseModel, Field, field_validator, model_validator

from ...services.local_events_service import get_local_events_service


class SearchLocalEventsInput(BaseModel):
    """Schema for search_local_events_tool."""

    city: str = Field(..., description="Target city")
    start_date: str = Field(..., description="Trip start date in YYYY-MM-DD")
    end_date: str = Field(..., description="Trip end date in YYYY-MM-DD")
    interest_keywords: list[str] = Field(..., description="Interest keywords extracted from request or memory")
    activation_reason: str | None = Field(default=None, description="Why this optional tool was activated")
    travel_days: int | None = Field(default=None, description="Requested travel days")
    daily_start_time: str | None = Field(default=None, description="Daily start time in HH:MM")
    daily_end_time: str | None = Field(default=None, description="Daily end time in HH:MM")

    @field_validator("city")
    @classmethod
    def validate_city(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("city must not be empty")
        return value

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_date(cls, value: str) -> str:
        datetime.strptime(value, "%Y-%m-%d")
        return value

    @field_validator("daily_start_time", "daily_end_time")
    @classmethod
    def validate_optional_time(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        datetime.strptime(value, "%H:%M")
        return value

    @field_validator("interest_keywords")
    @classmethod
    def validate_interest_keywords(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value if str(item).strip()]
        if not normalized:
            raise ValueError("interest_keywords must contain at least one keyword")
        return normalized

    @model_validator(mode="after")
    def validate_date_range(self) -> "SearchLocalEventsInput":
        start = datetime.strptime(self.start_date, "%Y-%m-%d")
        end = datetime.strptime(self.end_date, "%Y-%m-%d")
        if start > end:
            raise ValueError("start_date must be on or before end_date")
        return self


def _render_tool_text(city: str, items: list[dict[str, Any]], warning: str | None) -> str:
    if not items:
        base = f"No optional local event candidates were found for {city}."
        return f"{base} Warning: {warning}" if warning else base

    lines = [f"Found {len(items)} optional local event candidates for {city}."]
    for index, item in enumerate(items, start=1):
        interest_terms = ", ".join(item.get("interest_match_terms") or []) or "general city interest"
        time_window = item.get("time_window") or "time unknown"
        conflict_reason = item.get("conflict_reason") or "No conflict note."
        lines.append(
            f"{index}. {item.get('name', 'unknown')} | {item.get('category', 'local_event')} | "
            f"{item.get('date', 'date unknown')} {time_window} | "
            f"match: {interest_terms} | schedule: {item.get('conflict_status', 'unknown')} ({conflict_reason})"
        )
    if warning:
        lines.append(f"Warning: {warning}")
    return "\n".join(lines)


@tool("search_local_events_tool", args_schema=SearchLocalEventsInput)
def search_local_events_tool(
    city: str,
    start_date: str,
    end_date: str,
    interest_keywords: list[str],
    activation_reason: str | None = None,
    travel_days: int | None = None,
    daily_start_time: str | None = None,
    daily_end_time: str | None = None,
) -> dict[str, Any]:
    """按需触发的惊喜感创造工具。仅当用户对展览、演出、音乐、亲子等活动有明确兴趣，或整体行程明显偏慢、适合插入可选活动时才使用。调用后需要检查活动时间是否与整体行程区间冲突，结果应作为可选增强信息，而不是基础必需信息。"""

    service = get_local_events_service()
    result = service.search_local_events(
        city=city,
        start_date=start_date,
        end_date=end_date,
        interest_keywords=interest_keywords,
        daily_start_time=daily_start_time,
        daily_end_time=daily_end_time,
    )
    items = list(result.get("items") or [])
    warning = result.get("warning")
    return {
        "text": _render_tool_text(city, items, warning),
        "items": items,
        "warning": warning,
        "meta": {
            "activation_reason": activation_reason,
            "travel_days": travel_days,
        },
    }
