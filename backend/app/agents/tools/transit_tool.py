"""Tool wrapper for real transit time estimation."""

from __future__ import annotations

from typing import Any

from langchain_core.tools import tool
from pydantic import BaseModel, Field, field_validator

from ...services.amap_service import get_amap_service


class EstimateTransitTimeInput(BaseModel):
    """Schema for estimate_transit_time_tool."""

    city: str = Field(..., description="Target city")
    route_type: str = Field(default="walking", description="Route type: walking, driving, or transit")
    checkpoints: list[dict[str, Any]] = Field(default_factory=list, description="Ordered checkpoints to evaluate")
    threshold_minutes: int = Field(default=60, description="Drop-candidate threshold in minutes")

    @field_validator("city")
    @classmethod
    def validate_city(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("city must not be empty")
        return value

    @field_validator("route_type")
    @classmethod
    def validate_route_type(cls, value: str) -> str:
        value = str(value or "").strip().lower()
        return value if value in {"walking", "driving", "transit"} else "walking"

    @field_validator("threshold_minutes")
    @classmethod
    def validate_threshold(cls, value: int) -> int:
        return max(int(value), 1)


def _render_transit_text(items: list[dict[str, Any]], warning: str | None) -> str:
    if not items:
        base = "No transit evidence was returned."
        return f"{base} Warning: {warning}" if warning else base

    lines = [f"Collected {len(items)} real transit evidence items."]
    for index, item in enumerate(items, start=1):
        lines.append(
            f"{index}. {item.get('origin_name', 'unknown')} -> {item.get('destination_name', 'unknown')} | "
            f"{item.get('duration_minutes', 0)} min | {item.get('decision', 'unknown')}"
        )
    if warning:
        lines.append(f"Warning: {warning}")
    return "\n".join(lines)


@tool("estimate_transit_time_tool", args_schema=EstimateTransitTimeInput)
def estimate_transit_time_tool(
    city: str,
    route_type: str = "walking",
    checkpoints: list[dict[str, Any]] | None = None,
    threshold_minutes: int = 60,
) -> dict[str, Any]:
    """Use this tool to estimate real transit times between ordered itinerary checkpoints. Use real route service data only; do not invent transit durations."""

    checkpoints = checkpoints or []
    evidence: list[dict[str, Any]] = []
    warning = None

    if len(checkpoints) < 2:
        warning = "Not enough addressable checkpoints for transit estimation."
        return {
            "text": _render_transit_text(evidence, warning),
            "items": evidence,
            "warning": warning,
            "meta": {"source": "amap", "route_type": route_type, "threshold_minutes": threshold_minutes},
        }

    try:
        service = get_amap_service()
        for origin, destination in zip(checkpoints, checkpoints[1:]):
            origin_address = str(origin.get("address") or "")
            destination_address = str(destination.get("address") or "")
            if not origin_address or not destination_address:
                continue
            route = service.plan_route(
                origin_address=origin_address,
                destination_address=destination_address,
                origin_city=city,
                destination_city=city,
                route_type=route_type,
            )
            duration = int(route.get("duration") or 0)
            if duration <= 0:
                continue
            decision = "drop_candidate" if duration > threshold_minutes else "keep"
            reason = (
                f"Travel time {duration} minutes exceeds threshold {threshold_minutes}."
                if decision == "drop_candidate"
                else "Travel time acceptable."
            )
            evidence.append(
                {
                    "origin_name": str(origin.get("name") or origin_address),
                    "destination_name": str(destination.get("name") or destination_address),
                    "duration_minutes": duration,
                    "decision": decision,
                    "reason": reason,
                }
            )
    except Exception as exc:
        warning = f"Transit estimation failed: {exc}"

    if not evidence and warning is None:
        warning = "No valid transit routes were returned."

    return {
        "text": _render_transit_text(evidence, warning),
        "items": evidence,
        "warning": warning,
        "meta": {
            "source": "amap",
            "route_type": route_type,
            "threshold_minutes": threshold_minutes,
        },
    }
