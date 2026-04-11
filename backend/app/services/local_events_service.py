"""Local events service for optional itinerary enhancements."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from ..config import get_settings

_local_events_service: "LocalEventsService | None" = None


def create_local_events_llm() -> ChatOpenAI:
    """Create the LLM client used for local event candidate generation."""
    settings = get_settings()
    return ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        temperature=0.4,
    )


class LocalEventsService:
    """Provide normalized local event candidates for optional discovery."""

    def search_local_events(
        self,
        *,
        city: str,
        start_date: str,
        end_date: str,
        interest_keywords: list[str],
        daily_start_time: str | None = None,
        daily_end_time: str | None = None,
    ) -> dict[str, Any]:
        llm = create_local_events_llm()
        system_prompt = """You provide optional local event candidates for itinerary enhancement.
Return only a JSON array. Each item must contain:
name, category, date, time_window, address, description, interest_match_terms.

Rules:
- Focus on exhibitions, performances, music, family-friendly, or city-specific surprise options.
- Keep the result set small and useful.
- If time is unknown, leave time_window as an empty string.
"""
        user_query = (
            f"Find up to 5 local event candidates in {city} between {start_date} and {end_date}. "
            f"Interest keywords: {', '.join(interest_keywords)}. "
            "These are optional surprise candidates, not mandatory attractions."
        )
        response = llm.invoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_query),
            ]
        )
        raw_items = _extract_json_array(str(response.content))
        items = [
            _normalize_local_event_item(
                item,
                interest_keywords=interest_keywords,
                start_date=start_date,
                end_date=end_date,
                daily_start_time=daily_start_time,
                daily_end_time=daily_end_time,
            )
            for item in raw_items
        ]
        normalized_items = [item for item in items if item is not None][:5]
        warning = None if normalized_items else "No local event candidates were returned."
        return {
            "items": normalized_items,
            "warning": warning,
        }


def get_local_events_service() -> LocalEventsService:
    """Return the LocalEventsService singleton."""
    global _local_events_service
    if _local_events_service is None:
        _local_events_service = LocalEventsService()
    return _local_events_service


def _extract_json_array(text: str) -> list[dict[str, Any]]:
    if not text:
        return []

    payload = text.strip()
    try:
        if "```json" in payload:
            start = payload.find("```json") + 7
            end = payload.find("```", start)
            payload = payload[start:end].strip()
        elif "```" in payload:
            start = payload.find("```") + 3
            end = payload.find("```", start)
            payload = payload[start:end].strip()
        elif "[" in payload and "]" in payload:
            start = payload.find("[")
            end = payload.rfind("]") + 1
            payload = payload[start:end]
        data = json.loads(payload)
    except Exception:
        return []

    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


def _normalize_local_event_item(
    item: dict[str, Any],
    *,
    interest_keywords: list[str],
    start_date: str,
    end_date: str,
    daily_start_time: str | None,
    daily_end_time: str | None,
) -> dict[str, Any] | None:
    name = str(item.get("name") or "").strip()
    if not name:
        return None

    category = str(item.get("category") or "local_event").strip() or "local_event"
    date_text = str(item.get("date") or "").strip()
    time_window = str(item.get("time_window") or item.get("time") or "").strip()
    address = str(item.get("address") or "").strip()
    description = str(item.get("description") or "").strip()
    interest_match_terms = _normalize_interest_match_terms(
        item.get("interest_match_terms"),
        interest_keywords=interest_keywords,
        haystack=" ".join([name, category, description]),
    )
    conflict_status, conflict_reason = _evaluate_conflict(
        date_text=date_text,
        time_window=time_window,
        start_date=start_date,
        end_date=end_date,
        daily_start_time=daily_start_time,
        daily_end_time=daily_end_time,
    )
    return {
        "name": name,
        "category": category,
        "date": date_text,
        "time_window": time_window,
        "address": address,
        "description": description,
        "interest_match_terms": interest_match_terms,
        "conflict_status": conflict_status,
        "conflict_reason": conflict_reason,
    }


def _normalize_interest_match_terms(
    raw_terms: Any,
    *,
    interest_keywords: list[str],
    haystack: str,
) -> list[str]:
    if isinstance(raw_terms, list):
        terms = [str(term).strip() for term in raw_terms if str(term).strip()]
        if terms:
            return terms
    if isinstance(raw_terms, str) and raw_terms.strip():
        return [part.strip() for part in re.split(r"[,/|，、]", raw_terms) if part.strip()]

    lowered_haystack = haystack.lower()
    matched = [keyword for keyword in interest_keywords if keyword and keyword.lower() in lowered_haystack]
    return matched or list(interest_keywords[:2])


def _evaluate_conflict(
    *,
    date_text: str,
    time_window: str,
    start_date: str,
    end_date: str,
    daily_start_time: str | None,
    daily_end_time: str | None,
) -> tuple[str, str]:
    if not _is_date_in_range(date_text, start_date, end_date):
        return "conflicting", "Event date is outside the requested travel range."

    parsed_window = _parse_time_window(time_window)
    if not time_window.strip():
        return "unknown", "Event time window is missing."
    if parsed_window is None:
        return "unknown", "Event time window could not be parsed."

    daily_window = _parse_time_window(f"{daily_start_time}-{daily_end_time}") if daily_start_time and daily_end_time else None
    if daily_window is not None:
        event_start, event_end = parsed_window
        daily_start, daily_end = daily_window
        if event_start < daily_start or event_end > daily_end:
            return "conflicting", "Event time window falls outside the daily schedule."

    return "feasible", "No obvious schedule conflict was detected."


def _is_date_in_range(date_text: str, start_date: str, end_date: str) -> bool:
    try:
        target = datetime.strptime(date_text, "%Y-%m-%d").date()
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        return False
    return start <= target <= end


def _parse_time_window(time_window: str) -> tuple[int, int] | None:
    match = re.search(r"(\d{1,2}:\d{2})\s*[-~至]\s*(\d{1,2}:\d{2})", time_window)
    if not match:
        return None

    start_minutes = _parse_clock_to_minutes(match.group(1))
    end_minutes = _parse_clock_to_minutes(match.group(2))
    if start_minutes is None or end_minutes is None or end_minutes < start_minutes:
        return None
    return start_minutes, end_minutes


def _parse_clock_to_minutes(clock_text: str) -> int | None:
    try:
        parsed = datetime.strptime(clock_text, "%H:%M")
    except ValueError:
        return None
    return parsed.hour * 60 + parsed.minute
