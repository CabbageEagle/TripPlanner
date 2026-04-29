"""LangGraph state definitions for the trip planner."""

from __future__ import annotations

from typing import Any, Literal, TypedDict

from ..models.schemas import TripRequest


AllowedInfoToolName = Literal[
    "search_attractions_tool",
    "query_weather_tool",
    "search_hotels_tool",
    "search_local_events_tool",
    "estimate_transit_time_tool",
]

InfoGatheringAction = Literal["call_tool", "continue", "submit_context"]


class SOPRequiredState(TypedDict):
    """Mandatory and optional checks derived from request and context."""

    weather_required: bool
    attractions_required: bool
    hotels_required: bool
    transit_required: bool
    local_events_optional: bool


class SOPCompletedState(TypedDict):
    """Completion flags for required information gathering steps."""

    weather_done: bool
    attractions_done: bool
    hotels_done: bool
    transit_done: bool


class TransitEvidence(TypedDict, total=False):
    """Transit evidence used to keep or drop same-day candidates."""

    origin_name: str
    destination_name: str
    duration_minutes: int
    decision: Literal["keep", "drop_candidate"]
    reason: str


class GatheredContextState(TypedDict):
    """Structured context collected before plan generation."""

    attractions: list[dict[str, Any]]
    weather: dict[str, Any] | list[dict[str, Any]] | None
    hotels: list[dict[str, Any]]
    local_events: list[dict[str, Any]]
    transit_evidence: list[TransitEvidence]


class ToolCallRecord(TypedDict, total=False):
    """Normalized tool invocation log for the info-gathering loop."""

    tool_name: AllowedInfoToolName
    tool_input: dict[str, Any]
    success: bool
    reason: str
    summary: str
    result_count: int
    warning: str


class ToolResult(TypedDict, total=False):
    """Unified graph-level tool result passed from executor nodes to merge."""

    tool_name: AllowedInfoToolName
    tool_input: dict[str, Any]
    success: bool
    reason: str
    text: str
    items: list[dict[str, Any]]
    warning: str | None
    meta: dict[str, Any]


class ChecklistUpdate(TypedDict):
    """Agent-reported SOP progress after the current decision."""

    weather_done: bool
    attractions_done: bool
    hotels_done: bool
    transit_done: bool


class InfoGatheringAgentOutput(TypedDict):
    """Structured output contract for the info-gathering agent node."""

    action: InfoGatheringAction
    tool_name: AllowedInfoToolName | None
    tool_input: dict[str, Any]
    reasoning_summary: str
    ready_for_planning: bool
    checklist_update: ChecklistUpdate


class TripPlannerState(TypedDict, total=False):
    """Full runtime state for the trip-planning LangGraph."""

    # Request/input context
    request: TripRequest
    inferred_preferences: str | None
    memory_summary: str
    base_constraints: dict[str, Any]

    # Legacy collection fields kept for compatibility during migration
    attractions_data: str | None
    weather_data: str | None
    hotel_data: str | None

    # Info-gathering subgraph runtime fields
    sop_required: SOPRequiredState
    sop_completed: SOPCompletedState
    gathered_context: GatheredContextState
    context_summary: str
    last_tool_result: ToolResult | None
    tool_call_history: list[ToolCallRecord]
    candidate_filter_notes: list[str]
    agent_output: InfoGatheringAgentOutput | None
    ready_for_planning: bool
    loop_count: int
    max_loops: int
    router_warning: str | None
    forced_exit: bool
    force_exit_reason: str | None

    # Downstream planning / verification fields
    final_plan_raw: str | None
    final_plan: dict[str, Any] | None
    violations: list[dict[str, Any]] | None
    verify_count: int
    parse_retry_count: int
    schedule_applied: bool
    schedule_retry_count: int
    schedule_notes: list[str]
    days_to_reschedule: list[int] | None

    # Flow control
    current_step: str
    error: str | None
