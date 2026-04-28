"""LangGraph 节点函数定义"""

from typing import Dict, Any, Literal
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from .graph_state import TripPlannerState
from .tools import get_capability_tool
from ..config import get_settings
from ..services.amap_service import get_amap_service
from ..services.scheduler_service import ScheduleConfig, schedule_day_plan
import json


def create_llm():
    """创建LLM实例"""
    settings = get_settings()
    return ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        temperature=0.7
    )


def _get_capability_tool(tool_name: str):
    """Resolve a capability tool from the shared registry."""
    return get_capability_tool(tool_name)


INFO_GATHERING_TOOL_NAMES = {
    "search_attractions_tool",
    "query_weather_tool",
    "search_hotels_tool",
    "search_local_events_tool",
    "estimate_transit_time_tool",
}


class InfoGatheringDecision(BaseModel):
    """LLM-produced decision for the info-gathering agent."""

    model_config = ConfigDict(extra="ignore")

    action: Literal["call_tool", "continue", "submit_context"]
    tool_name: str | None = None
    reasoning_summary: str = Field(default="")
    ready_for_planning: bool = False

    @field_validator("tool_name")
    @classmethod
    def normalize_tool_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = str(value).strip()
        if not value or value.lower() == "null":
            return None
        return value

LOCAL_EVENT_HINTS = ("展", "演出", "音乐", "亲子", "活动", "show", "live", "event")
LOW_TRANSIT_HINTS = ("顺路", "不折腾", "老人", "小孩", "带娃", "轻松", "少走路")
NO_HOTEL_HINTS = ("无需住宿", "无须住宿", "不住宿", "当天往返")


def _request_wants_local_events(request: Any) -> bool:
    trigger_hints = LOCAL_EVENT_HINTS + (
        "展览",
        "展会",
        "演唱会",
        "音乐会",
        "音乐节",
        "亲子游",
        "儿童",
        "剧场",
        "话剧",
        "脱口秀",
        "concert",
        "family",
    )
    preferences = " ".join(str(preference) for preference in (getattr(request, "preferences", []) or []))
    free_text = str(getattr(request, "free_text_input", "") or "")
    haystack = f"{preferences} {free_text}".lower()
    return any(keyword.lower() in haystack for keyword in trigger_hints)


def _iter_local_event_signal_texts(state: TripPlannerState) -> list[str]:
    request = state["request"]
    texts = [
        " ".join(str(preference) for preference in (getattr(request, "preferences", []) or [])),
        str(getattr(request, "free_text_input", "") or ""),
        str(state.get("inferred_preferences") or ""),
        str(state.get("memory_summary") or ""),
    ]
    return [text for text in texts if text.strip()]


def _has_local_event_interest_signal(state: TripPlannerState) -> bool:
    hints = (
        "展",
        "展览",
        "展会",
        "演出",
        "演唱会",
        "话剧",
        "脱口秀",
        "音乐",
        "音乐会",
        "音乐节",
        "亲子",
        "儿童",
        "show",
        "live",
        "concert",
        "family",
    )
    return any(any(hint.lower() in text.lower() for hint in hints) for text in _iter_local_event_signal_texts(state))


def _has_slow_pace_signal(state: TripPlannerState) -> bool:
    hints = LOW_TRANSIT_HINTS + ("慢游", "休闲", "悠闲", "citywalk")
    return any(any(hint.lower() in text.lower() for hint in hints) for text in _iter_local_event_signal_texts(state))


def _extract_local_event_interest_keywords(state: TripPlannerState) -> list[str]:
    keyword_groups = {
        "展览": ("展", "展览", "展会", "museum", "gallery"),
        "演出": ("演出", "话剧", "脱口秀", "show", "live", "performance"),
        "音乐": ("音乐", "演唱会", "音乐会", "音乐节", "concert"),
        "亲子": ("亲子", "儿童", "带娃", "family", "kids"),
    }
    texts = _iter_local_event_signal_texts(state)
    keywords: list[str] = []
    for label, hints in keyword_groups.items():
        if any(any(hint.lower() in text.lower() for hint in hints) for text in texts):
            keywords.append(label)

    if keywords:
        return keywords

    request = state["request"]
    fallback_preferences = [str(item).strip() for item in (getattr(request, "preferences", []) or []) if str(item).strip()]
    if fallback_preferences:
        return fallback_preferences[:3]
    return ["城市漫游"]


def _get_local_event_activation_reason(state: TripPlannerState) -> str:
    if _has_local_event_interest_signal(state):
        return "interest_match"
    if _has_slow_pace_signal(state):
        return "slow_pace"
    if _attractions_insufficient(state):
        return "candidate_gap"
    return "interest_match"


def _minimum_attraction_candidates(request: Any) -> int:
    travel_days = max(int(getattr(request, "travel_days", 1) or 1), 1)
    return max(4, travel_days * 2)


def _attractions_insufficient(state: TripPlannerState) -> bool:
    gathered_context = state.get("gathered_context") or {}
    attractions = [item for item in (gathered_context.get("attractions") or []) if isinstance(item, dict)]
    return len(attractions) < _minimum_attraction_candidates(state["request"])


def _should_search_local_events(state: TripPlannerState) -> bool:
    gathered_context = state.get("gathered_context") or {}
    if gathered_context.get("local_events"):
        return False
    return (
        _has_local_event_interest_signal(state)
        or _has_slow_pace_signal(state)
        or _attractions_insufficient(state)
    )


def _default_sop_required(request: Any) -> dict[str, bool]:
    accommodation = str(getattr(request, "accommodation", "") or "")
    hotels_required = bool(accommodation) and not any(keyword in accommodation for keyword in NO_HOTEL_HINTS)
    local_events_optional = _request_wants_local_events(request)
    return {
        "weather_required": True,
        "attractions_required": True,
        "hotels_required": hotels_required,
        "transit_required": False,
        "local_events_optional": local_events_optional,
    }


def _default_sop_completed() -> dict[str, bool]:
    return {
        "weather_done": False,
        "attractions_done": False,
        "hotels_done": False,
        "transit_done": False,
    }


def _default_gathered_context() -> dict[str, Any]:
    return {
        "attractions": [],
        "weather": None,
        "hotels": [],
        "local_events": [],
        "transit_evidence": [],
    }


def _default_checklist_update(state: TripPlannerState) -> dict[str, bool]:
    completed = state.get("sop_completed") or _default_sop_completed()
    return {
        "weather_done": bool(completed.get("weather_done")),
        "attractions_done": bool(completed.get("attractions_done")),
        "hotels_done": bool(completed.get("hotels_done")),
        "transit_done": bool(completed.get("transit_done")),
    }


def _copy_gathered_context(state: TripPlannerState) -> dict[str, Any]:
    current = state.get("gathered_context") or _default_gathered_context()
    return {
        "attractions": list(current.get("attractions") or []),
        "weather": current.get("weather"),
        "hotels": list(current.get("hotels") or []),
        "local_events": list(current.get("local_events") or []),
        "transit_evidence": list(current.get("transit_evidence") or []),
    }


def _model_to_dict(item: Any) -> dict[str, Any]:
    if hasattr(item, "model_dump"):
        return item.model_dump(mode="json")
    if isinstance(item, dict):
        return item
    return dict(item)


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


def _append_tool_history(
    state: TripPlannerState,
    *,
    tool_name: str,
    tool_input: dict[str, Any],
    success: bool,
    summary: str,
    result_count: int = 0,
    warning: str | None = None,
) -> list[dict[str, Any]]:
    history = list(state.get("tool_call_history") or [])
    record = {
        "tool_name": tool_name,
        "tool_input": tool_input,
        "success": success,
        "summary": summary,
        "result_count": result_count,
    }
    if warning:
        record["warning"] = warning
    history.append(record)
    return history


def _extract_region_tag(address: str) -> str:
    for marker in ("区", "县", "市"):
        idx = address.find(marker)
        if idx > 0:
            start = max(address.rfind(" ", 0, idx), address.rfind("省", 0, idx), address.rfind("市", 0, idx))
            return address[start + 1 : idx + 1]
    return ""


def _has_fixed_time_local_events(state: TripPlannerState) -> bool:
    context = state.get("gathered_context") or {}
    local_events = context.get("local_events") or []
    return any(
        isinstance(item, dict)
        and str(item.get("date") or "").strip()
        and str(item.get("time_window") or "").strip()
        for item in local_events
    )


def _derive_transit_required(state: TripPlannerState) -> bool:
    request = state["request"]
    free_text = str(getattr(request, "free_text_input", "") or "")
    if any(keyword in free_text for keyword in LOW_TRANSIT_HINTS):
        return True
    if _has_fixed_time_local_events(state):
        return True

    context = state.get("gathered_context") or {}
    attractions = context.get("attractions") or []
    hotels = context.get("hotels") or []
    region_tags = {
        _extract_region_tag(str(item.get("address") or ""))
        for item in [*attractions, *hotels]
        if isinstance(item, dict)
    }
    region_tags.discard("")
    return len(region_tags) >= 2


def _build_transit_drop_targets(state: TripPlannerState) -> set[str]:
    context = state.get("gathered_context") or {}
    evidence = context.get("transit_evidence") or []
    return {
        str(item.get("destination_name") or "").strip()
        for item in evidence
        if isinstance(item, dict)
        and item.get("decision") == "drop_candidate"
        and str(item.get("destination_name") or "").strip()
    }


def _filter_planning_candidates(
    state: TripPlannerState,
    *,
    attractions: list[dict[str, Any]],
    local_events: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    drop_targets = _build_transit_drop_targets(state)
    if not drop_targets:
        return attractions, local_events

    filtered_local_events = [
        item for item in local_events if str(item.get("name") or "").strip() not in drop_targets
    ]
    filtered_attractions = [
        item for item in attractions if str(item.get("name") or "").strip() not in drop_targets
    ]
    minimum_keep = max(2, int(getattr(state["request"], "travel_days", 1) or 1) + 1)
    attractions_for_planning = filtered_attractions if len(filtered_attractions) >= minimum_keep else attractions
    return attractions_for_planning, filtered_local_events


def _build_transit_checkpoints(state: TripPlannerState) -> list[dict[str, Any]]:
    gathered_context = _copy_gathered_context(state)
    attractions = [item for item in gathered_context.get("attractions") or [] if isinstance(item, dict)]
    hotels = [item for item in gathered_context.get("hotels") or [] if isinstance(item, dict)]
    local_events = [item for item in gathered_context.get("local_events") or [] if isinstance(item, dict)]
    checkpoints: list[dict[str, Any]] = []
    if hotels:
        checkpoints.append(hotels[0])
    checkpoints.extend(attractions[:3])
    fixed_time_events = [
        item
        for item in local_events
        if str(item.get("date") or "").strip() and str(item.get("time_window") or "").strip()
    ]
    if fixed_time_events:
        checkpoints.append(fixed_time_events[0])
    return checkpoints


def _transit_threshold_minutes(state: TripPlannerState) -> int:
    request = state["request"]
    return 45 if any(
        keyword in str(getattr(request, "free_text_input", "") or "")
        for keyword in LOW_TRANSIT_HINTS
    ) else 60


def all_required_sop_completed(state: TripPlannerState) -> bool:
    required = state.get("sop_required") or {}
    completed = state.get("sop_completed") or {}
    for required_key, completed_key in (
        ("weather_required", "weather_done"),
        ("attractions_required", "attractions_done"),
        ("hotels_required", "hotels_done"),
        ("transit_required", "transit_done"),
    ):
        if required.get(required_key) and not completed.get(completed_key):
            return False
    return True


def _missing_required_steps(state: TripPlannerState) -> list[str]:
    required = state.get("sop_required") or {}
    completed = state.get("sop_completed") or {}
    messages: list[str] = []
    if required.get("attractions_required") and not completed.get("attractions_done"):
        messages.append("景点信息尚未完成")
    if required.get("weather_required") and not completed.get("weather_done"):
        messages.append("天气信息尚未完成")
    if required.get("hotels_required") and not completed.get("hotels_done"):
        messages.append("酒店信息尚未完成")
    if required.get("transit_required") and not completed.get("transit_done"):
        messages.append("交通测算尚未完成")
    return messages


def _build_router_warning_message(state: TripPlannerState) -> str:
    output = state.get("agent_output") or {}
    missing_steps = _missing_required_steps(state)
    action = output.get("action")

    if action == "submit_context" and missing_steps:
        return f"不能提前交卷：{'；'.join(missing_steps)}。"
    if action == "call_tool" and output.get("tool_name") not in INFO_GATHERING_TOOL_NAMES:
        return f"非法工具调用：{output.get('tool_name') or 'unknown'}。"
    if action not in {"call_tool", "continue", "submit_context", None}:
        return f"非法 agent action：{action}。"
    if (
        (state.get("sop_required") or {}).get("transit_required")
        and not (state.get("sop_completed") or {}).get("transit_done")
        and output.get("ready_for_planning") is True
    ):
        return "当前候选存在交通风险，但交通测算尚未完成。"
    if missing_steps:
        return f"仍有必查项未完成：{'；'.join(missing_steps)}。"
    return "需要重新判断下一步动作。"


def _build_forced_exit_reason(state: TripPlannerState) -> str:
    loop_count = int(state.get("loop_count", 0))
    max_loops = int(state.get("max_loops", 5))
    missing_steps = _missing_required_steps(state)
    history = state.get("tool_call_history") or []
    called_tools = [str(item.get("tool_name")) for item in history if isinstance(item, dict) and item.get("tool_name")]
    if missing_steps:
        missing_text = "；".join(missing_steps)
    else:
        missing_text = "无必查项缺失"
    tool_text = ", ".join(called_tools[-5:]) if called_tools else "无工具调用"
    return f"信息搜集达到循环上限 {loop_count}/{max_loops}，未完成项：{missing_text}，最近工具调用：{tool_text}。"


def _build_context_summary(state: TripPlannerState) -> str:
    context = state.get("gathered_context") or _default_gathered_context()
    weather = context.get("weather")
    weather_count = len(weather) if isinstance(weather, list) else int(bool(weather))
    parts = [
        f"景点 {len(context.get('attractions') or [])} 个",
        f"天气 {weather_count} 条",
        f"酒店 {len(context.get('hotels') or [])} 个",
        f"本地活动 {len(context.get('local_events') or [])} 个",
        f"交通证据 {len(context.get('transit_evidence') or [])} 条",
    ]
    notes = list(state.get("candidate_filter_notes") or [])
    if notes:
        parts.append(f"筛选备注 {len(notes)} 条")
    if state.get("router_warning"):
        parts.append(f"警告: {state['router_warning']}")
    if state.get("forced_exit"):
        parts.append(f"熔断: {state.get('force_exit_reason') or 'best effort'}")
    return "；".join(parts)


def _tool_input_for_step(tool_name: str, state: TripPlannerState) -> dict[str, Any]:
    request = state["request"]
    if tool_name == "search_attractions_tool":
        return {"city": request.city, "keywords": list(request.preferences or [])}
    if tool_name == "query_weather_tool":
        return {"city": request.city, "date_range": [request.start_date, request.end_date]}
    if tool_name == "search_hotels_tool":
        return {"city": request.city, "accommodation": request.accommodation}
    if tool_name == "search_local_events_tool":
        return {
            "city": request.city,
            "start_date": request.start_date,
            "end_date": request.end_date,
            "interest_keywords": _extract_local_event_interest_keywords(state),
            "activation_reason": _get_local_event_activation_reason(state),
            "travel_days": request.travel_days,
            "daily_start_time": getattr(request, "daily_start_time", None),
            "daily_end_time": getattr(request, "daily_end_time", None),
        }
    return {
        "city": request.city,
        "route_type": _infer_route_type(request.transportation),
        "checkpoints": _build_transit_checkpoints(state),
        "threshold_minutes": _transit_threshold_minutes(state),
    }





def init_info_gathering_node(state: TripPlannerState) -> Dict[str, Any]:
    request = state["request"]
    gathered_context = _copy_gathered_context(state)
    sop_required = _default_sop_required(request)
    sop_required["transit_required"] = _derive_transit_required(
        {
            **state,
            "gathered_context": gathered_context,
            "sop_required": sop_required,
        }
    )
    return {
        "sop_required": sop_required,
        "sop_completed": state.get("sop_completed") or _default_sop_completed(),
        "gathered_context": gathered_context,
        "context_summary": state.get("context_summary") or "",
        "tool_call_history": list(state.get("tool_call_history") or []),
        "candidate_filter_notes": list(state.get("candidate_filter_notes") or []),
        "agent_output": state.get("agent_output"),
        "ready_for_planning": bool(state.get("ready_for_planning", False)),
        "loop_count": int(state.get("loop_count", 0)),
        "max_loops": int(state.get("max_loops", 5)),
        "router_warning": state.get("router_warning"),
        "forced_exit": bool(state.get("forced_exit", False)),
        "force_exit_reason": state.get("force_exit_reason"),
        "memory_summary": state.get("memory_summary", ""),
        "base_constraints": state.get("base_constraints", {}),
        "current_step": "info_gathering_initialized",
    }


def _build_info_gathering_node_result(
    state: TripPlannerState,
    *,
    action: str,
    tool_name: str | None,
    reasoning_summary: str,
    ready_for_planning: bool,
) -> Dict[str, Any]:
    safe_tool_name = tool_name if action == "call_tool" and tool_name in INFO_GATHERING_TOOL_NAMES else None
    ready = bool(ready_for_planning and all_required_sop_completed(state))
    output = {
        "action": action,
        "tool_name": safe_tool_name,
        "tool_input": _tool_input_for_step(safe_tool_name, state) if safe_tool_name else {},
        "reasoning_summary": reasoning_summary,
        "ready_for_planning": ready,
        "checklist_update": _default_checklist_update(state),
    }
    return {
        "agent_output": output,
        "ready_for_planning": ready,
        "current_step": "info_gathering_decided",
    }


def _rule_based_info_gathering_decision(state: TripPlannerState) -> Dict[str, Any]:
    sop_required = state.get("sop_required") or _default_sop_required(state["request"])
    sop_completed = state.get("sop_completed") or _default_sop_completed()

    next_tool: str | None = None
    reason = "All mandatory information has been collected."

    if sop_required.get("attractions_required") and not sop_completed.get("attractions_done"):
        next_tool = "search_attractions_tool"
        reason = "Need baseline attractions before planning."
    elif sop_required.get("weather_required") and not sop_completed.get("weather_done"):
        next_tool = "query_weather_tool"
        reason = "Need weather to validate outdoor feasibility."
    elif sop_required.get("hotels_required") and not sop_completed.get("hotels_done"):
        next_tool = "search_hotels_tool"
        reason = "User needs hotel options before planning."
    elif sop_required.get("transit_required") and not sop_completed.get("transit_done"):
        next_tool = "estimate_transit_time_tool"
        reason = "Need transit evidence before submitting context."
    elif _should_search_local_events(state):
        next_tool = "search_local_events_tool"
        reason = "Optional local events may improve the itinerary."

    if next_tool is not None and state.get("loop_count", 0) < state.get("max_loops", 5):
        return _build_info_gathering_node_result(
            state,
            action="call_tool",
            tool_name=next_tool,
            reasoning_summary=reason,
            ready_for_planning=False,
        )

    ready = all_required_sop_completed(state)
    return _build_info_gathering_node_result(
        state,
        action="submit_context" if ready else "continue",
        tool_name=None,
        reasoning_summary=state.get("router_warning") or reason,
        ready_for_planning=ready,
    )


def _build_info_gathering_decision_prompt(state: TripPlannerState) -> list[Any]:
    request = state["request"]
    request_payload = {
        "city": request.city,
        "start_date": request.start_date,
        "end_date": request.end_date,
        "travel_days": request.travel_days,
        "transportation": request.transportation,
        "accommodation": request.accommodation,
        "preferences": list(request.preferences or []),
        "free_text_input": getattr(request, "free_text_input", "") or "",
        "daily_start_time": getattr(request, "daily_start_time", None),
        "daily_end_time": getattr(request, "daily_end_time", None),
    }
    system_prompt = """You are the info-gathering decision agent for a trip planner.
Decide the next information-gathering action only. Do not answer the user, do not plan the trip, and do not invent tool results.

Available tools:
- search_attractions_tool: collect baseline attraction candidates from real AMap POI data. It cannot be replaced by local events.
- query_weather_tool: collect real weather context from AMap. Never invent or estimate weather.
- search_hotels_tool: collect real hotel candidates from AMap POI data when accommodation is required.
- estimate_transit_time_tool: collect transit evidence when transit is required.
- search_local_events_tool: optional surprise candidates only.
{
  "tools": [
    {
      "name": "search_attractions_tool",
      "type": "required",
      "use_when": "attractions_required=true and attractions_done=false",
      "data_source": "real AMap POI data",
      "cannot_be_replaced_by": ["search_local_events_tool"],
      "must_not": ["invent_attractions"]
    },
    {
      "name": "query_weather_tool",
      "type": "required",
      "use_when": "weather_required=true and weather_done=false",
      "data_source": "real AMap weather data",
      "must_not": ["invent_weather", "estimate_weather"]
    },
    {
      "name": "search_hotels_tool",
      "type": "conditional_required",
      "use_when": "hotels_required=true and hotels_done=false",
      "data_source": "real AMap POI data",
      "must_not": ["invent_hotels"]
    },
    {
      "name": "estimate_transit_time_tool",
      "type": "conditional_required",
      "use_when": "transit_required=true and transit_done=false",
      "use_after": ["search_attractions_tool", "search_hotels_tool"]
    },
    {
      "name": "search_local_events_tool",
      "type": "optional",
      "use_when": "required SOP complete and local event trigger exists",
      "must_not": ["replace_attractions", "block_planning"]
    }
  ]
}

Rules:
1. Required SOP steps cannot be skipped.
2. Never set ready_for_planning=true unless all required SOP steps are complete.
3. Local events are optional and must not make required SOP look complete.
4. If unsure, choose continue.
5. Output JSON only, with keys: action, tool_name, reasoning_summary, ready_for_planning.
"""
    user_prompt = {
        "request": request_payload,
        "sop_required": state.get("sop_required") or {},
        "sop_completed": state.get("sop_completed") or {},
        "context_summary": state.get("context_summary") or "",
        "recent_tool_call_history": list(state.get("tool_call_history") or [])[-5:],
        "candidate_filter_notes": list(state.get("candidate_filter_notes") or []),
        "inferred_preferences": state.get("inferred_preferences") or "",
        "valid_actions": ["call_tool", "continue", "submit_context"],
        "valid_tool_names": sorted(INFO_GATHERING_TOOL_NAMES),
    }
    return [
        SystemMessage(content=system_prompt),
        HumanMessage(content=json.dumps(user_prompt, ensure_ascii=False, indent=2)),
    ]


def _call_info_gathering_llm(state: TripPlannerState) -> InfoGatheringDecision:
    llm = create_llm()
    response = llm.invoke(_build_info_gathering_decision_prompt(state))
    payload = _extract_json_object(str(response.content))
    if not isinstance(payload, dict):
        raise ValueError("Info gathering LLM did not return a JSON object.")
    return InfoGatheringDecision.model_validate(payload)


def _sanitize_info_gathering_decision(
    state: TripPlannerState,
    decision: InfoGatheringDecision,
) -> Dict[str, Any]:
    fallback = _rule_based_info_gathering_decision(state)
    fallback_output = fallback.get("agent_output") or {}
    fallback_action = fallback_output.get("action")
    fallback_tool = fallback_output.get("tool_name")

    if decision.action == "call_tool" and decision.tool_name not in INFO_GATHERING_TOOL_NAMES:
        return fallback
    if decision.action == "submit_context" and not all_required_sop_completed(state):
        return fallback
    if decision.action == "continue" and _missing_required_steps(state):
        return fallback

    if fallback_action == "call_tool" and decision.tool_name != fallback_tool:
        return fallback
    if fallback_action != "call_tool" and decision.action == "call_tool":
        return fallback
    if fallback_action == "submit_context" and decision.action != "submit_context":
        return fallback

    return _build_info_gathering_node_result(
        state,
        action=decision.action,
        tool_name=decision.tool_name,
        reasoning_summary=decision.reasoning_summary or str(fallback_output.get("reasoning_summary") or ""),
        ready_for_planning=all_required_sop_completed(state) if decision.action == "submit_context" else decision.ready_for_planning,
    )


def info_gathering_agent_node(state: TripPlannerState) -> Dict[str, Any]:
    if getattr(get_settings(), "info_gathering_use_llm", False):
        try:
            decision = _call_info_gathering_llm(state)
            return _sanitize_info_gathering_decision(state, decision)
        except (ValidationError, ValueError, TypeError, json.JSONDecodeError) as exc:
            print(f"[GRAPH] info gathering LLM decision failed, using rule fallback: {exc}")
        except Exception as exc:
            print(f"[GRAPH] info gathering LLM unavailable, using rule fallback: {exc}")

    return _rule_based_info_gathering_decision(state)


def _build_hard_restraints_block(state: TripPlannerState)->str:
    request = state["request"]

    must_rules = [
        f"每日景点数量必须 <= {request.max_attractions_per_day}。",
        f"相邻景点或活动之间必须预留 >= {request.min_rest_time} 分钟休息或机动时间。",
        f"每天行程时间必须在 {request.daily_start_time} - {request.daily_end_time} 内闭合，禁止越界。",
    ]

    if request.accommodation:
        if "无需住宿" in str(request.accommodation):
            must_rules.append("住宿约束：本次行程为“无需住宿”，必须不推荐酒店，且酒店预算必须为 0。")
        else:
            must_rules.append(f"住宿约束：住宿类型必须匹配“{request.accommodation}”，不得擅自升级或替换档位。")

    if request.max_budget is not None:
        must_rules.append(f"总预算必须 <= {request.max_budget} 元。")
    if request.budget_per_day is not None:
        must_rules.append(f"单日预算必须 <= {request.budget_per_day} 元。")
    if request.max_walking_time is not None:
        must_rules.append(f"单次步行时长必须 <= {request.max_walking_time} 分钟。")

    prefer_rules = []
    if request.avoid_rush_hour:
        prefer_rules.append("尽量避开早晚高峰时段安排跨区交通。")
    if request.free_text_input:
        prefer_rules.append(f"尽量满足用户附加偏好：{request.free_text_input}")

    must_text = "\n".join(f"- {item}" for item in must_rules)
    prefer_text = "\n".join(f"- {item}" for item in prefer_rules) if prefer_rules else "- 无"

    return f"""[HARD_CONSTRAINTS | 最高优先级]
你必须先满足 MUST，再考虑 PREFER。任何 MUST 不得被弱化、忽略或与其他目标权衡。

MUST:
{must_text}

PREFER:
{prefer_text}
"""


def _build_hard_constraints_block(state: TripPlannerState) -> str:
    """Backward-compatible alias for older call sites."""
    return _build_hard_restraints_block(state)


def search_attractions_node(state: TripPlannerState) -> Dict[str, Any]:
    """Search attractions through the registered tool adapter."""
    print("[GRAPH] searching attractions...")

    request = state["request"]
    tool_input = _tool_input_for_step("search_attractions_tool", state)
    gathered_context = _copy_gathered_context(state)
    sop_completed = dict(state.get("sop_completed") or _default_sop_completed())
    warning: str | None = None
    natural_text = ""
    try:
        tool = _get_capability_tool("search_attractions_tool")
        tool_result = tool.invoke(tool_input)
        attractions = list(tool_result.get("items") or [])
        natural_text = str(tool_result.get("text") or "")
        warning = tool_result.get("warning")
    except Exception as exc:
        attractions = []
        natural_text = "Attraction lookup failed."
        warning = f"search_attractions_tool failed: {exc}"

    gathered_context["attractions"] = attractions
    sop_completed["attractions_done"] = bool(attractions)

    next_state = {
        **state,
        "gathered_context": gathered_context,
        "sop_completed": sop_completed,
        "candidate_filter_notes": list(state.get("candidate_filter_notes") or []),
    }
    next_state["sop_required"] = dict(state.get("sop_required") or _default_sop_required(request))
    next_state["sop_required"]["transit_required"] = _derive_transit_required(next_state)
    context_summary = _build_context_summary(next_state)
    summary = f"Collected {len(attractions)} attraction candidates."
    return {
        "attractions_data": json.dumps(attractions, ensure_ascii=False),
        "gathered_context": gathered_context,
        "sop_completed": sop_completed,
        "sop_required": next_state["sop_required"],
        "tool_call_history": _append_tool_history(
            state,
            tool_name="search_attractions_tool",
            tool_input=tool_input,
            success=bool(attractions),
            summary=natural_text or summary,
            result_count=len(attractions),
            warning=warning,
        ),
        "context_summary": context_summary,
        "loop_count": int(state.get("loop_count", 0)) + 1,
        "router_warning": None,
        "current_step": "attractions_searched",
    }


def query_weather_node(state: TripPlannerState) -> Dict[str, Any]:
    """Query weather through the registered tool adapter."""
    print("[GRAPH] querying weather...")

    tool_input = _tool_input_for_step("query_weather_tool", state)
    gathered_context = _copy_gathered_context(state)
    sop_completed = dict(state.get("sop_completed") or _default_sop_completed())
    warning: str | None = None
    natural_text = ""
    try:
        tool = _get_capability_tool("query_weather_tool")
        tool_result = tool.invoke(tool_input)
        weather_items = list(tool_result.get("items") or [])
        natural_text = str(tool_result.get("text") or "")
        warning = tool_result.get("warning")
    except Exception as exc:
        weather_items = []
        natural_text = "Weather lookup failed."
        warning = f"query_weather_tool failed: {exc}"

    gathered_context["weather"] = weather_items
    sop_completed["weather_done"] = bool(weather_items)
    next_state = {
        **state,
        "gathered_context": gathered_context,
        "sop_completed": sop_completed,
    }
    context_summary = _build_context_summary(next_state)
    summary = f"Collected {len(weather_items)} weather entries."
    return {
        "weather_data": json.dumps(weather_items, ensure_ascii=False),
        "gathered_context": gathered_context,
        "sop_completed": sop_completed,
        "tool_call_history": _append_tool_history(
            state,
            tool_name="query_weather_tool",
            tool_input=tool_input,
            success=bool(weather_items),
            summary=natural_text or summary,
            result_count=len(weather_items),
            warning=warning,
        ),
        "context_summary": context_summary,
        "loop_count": int(state.get("loop_count", 0)) + 1,
        "router_warning": None,
        "current_step": "weather_queried",
    }


def search_hotels_node(state: TripPlannerState) -> Dict[str, Any]:
    """Search hotels through the registered tool adapter."""
    print("[GRAPH] searching hotels...")

    tool_input = _tool_input_for_step("search_hotels_tool", state)
    gathered_context = _copy_gathered_context(state)
    sop_completed = dict(state.get("sop_completed") or _default_sop_completed())
    warning: str | None = None
    natural_text = ""

    try:
        tool = _get_capability_tool("search_hotels_tool")
        tool_result = tool.invoke(tool_input)
        hotels = list(tool_result.get("items") or [])
        natural_text = str(tool_result.get("text") or "")
        warning = tool_result.get("warning")
    except Exception as exc:
        hotels = []
        natural_text = "Hotel lookup failed."
        warning = f"search_hotels_tool failed: {exc}"

    gathered_context["hotels"] = hotels
    if (state.get("sop_required") or {}).get("hotels_required"):
        sop_completed["hotels_done"] = bool(hotels)

    next_state = {
        **state,
        "gathered_context": gathered_context,
        "sop_completed": sop_completed,
    }
    context_summary = _build_context_summary(next_state)
    summary = f"Collected {len(hotels)} hotel candidates."
    return {
        "hotel_data": json.dumps(hotels, ensure_ascii=False),
        "gathered_context": gathered_context,
        "sop_completed": sop_completed,
        "tool_call_history": _append_tool_history(
            state,
            tool_name="search_hotels_tool",
            tool_input=tool_input,
            success=bool(hotels),
            summary=natural_text or summary,
            result_count=len(hotels),
            warning=warning,
        ),
        "context_summary": context_summary,
        "loop_count": int(state.get("loop_count", 0)) + 1,
        "router_warning": None,
        "current_step": "hotels_searched",
    }

def search_local_events_node(state: TripPlannerState) -> Dict[str, Any]:
    """Search optional local events as an enhancement source."""
    print("[GRAPH] searching local events...")

    tool_input = _tool_input_for_step("search_local_events_tool", state)
    gathered_context = _copy_gathered_context(state)
    warning: str | None = None
    natural_text = ""

    try:
        tool = _get_capability_tool("search_local_events_tool")
        tool_result = tool.invoke(tool_input)
        local_events = list(tool_result.get("items") or [])
        natural_text = str(tool_result.get("text") or "")
        warning = tool_result.get("warning")
    except Exception as exc:
        local_events = []
        natural_text = "Local events lookup failed."
        warning = f"search_local_events_tool failed: {exc}"

    gathered_context["local_events"] = local_events
    next_state = {
        **state,
        "gathered_context": gathered_context,
    }
    return {
        "gathered_context": gathered_context,
        "tool_call_history": _append_tool_history(
            state,
            tool_name="search_local_events_tool",
            tool_input=tool_input,
            success=bool(local_events),
            summary=natural_text or f"Collected {len(local_events)} local event candidates.",
            result_count=len(local_events),
            warning=warning,
        ),
        "context_summary": _build_context_summary(next_state),
        "loop_count": int(state.get("loop_count", 0)) + 1,
        "router_warning": None,
        "current_step": "local_events_searched",
    }


def estimate_transit_time_node(state: TripPlannerState) -> Dict[str, Any]:
    """Estimate transit time and keep/drop risky cross-region candidates."""
    print("[GRAPH] estimating transit...")

    tool_input = _tool_input_for_step("estimate_transit_time_tool", state)
    gathered_context = _copy_gathered_context(state)
    sop_completed = dict(state.get("sop_completed") or _default_sop_completed())
    candidate_filter_notes = list(state.get("candidate_filter_notes") or [])
    evidence: list[dict[str, Any]] = []
    warning: str | None = None
    natural_text = ""

    try:
        tool = _get_capability_tool("estimate_transit_time_tool")
        tool_result = tool.invoke(tool_input)
        evidence = list(tool_result.get("items") or [])
        natural_text = str(tool_result.get("text") or "")
        warning = tool_result.get("warning")
    except Exception as exc:
        natural_text = "Transit estimation failed."
        warning = f"estimate_transit_time_tool failed: {exc}"

    for item in evidence:
        if not isinstance(item, dict) or item.get("decision") != "drop_candidate":
            continue
        candidate_filter_notes.append(
            f"{item.get('origin_name') or 'unknown'} -> {item.get('destination_name') or 'unknown'} 通勤 {item.get('duration_minutes') or 0} 分钟，建议从同日候选中剔除。"
        )

    gathered_context["transit_evidence"] = evidence
    sop_completed["transit_done"] = bool(evidence)
    next_state = {
        **state,
        "gathered_context": gathered_context,
        "sop_completed": sop_completed,
        "candidate_filter_notes": candidate_filter_notes,
    }
    return {
        "gathered_context": gathered_context,
        "sop_completed": sop_completed,
        "candidate_filter_notes": candidate_filter_notes,
        "tool_call_history": _append_tool_history(
            state,
            tool_name="estimate_transit_time_tool",
            tool_input=tool_input,
            success=bool(evidence),
            summary=natural_text or f"Collected {len(evidence)} transit evidence items.",
            result_count=len(evidence),
            warning=warning,
        ),
        "context_summary": _build_context_summary(next_state),
        "loop_count": int(state.get("loop_count", 0)) + 1,
        "router_warning": None,
        "current_step": "transit_estimated",
    }


def merge_tool_result_node(state: TripPlannerState) -> Dict[str, Any]:
    """Normalize summary fields after a tool node updated the state."""
    sop_required = dict(state.get("sop_required") or _default_sop_required(state["request"]))
    sop_required["transit_required"] = _derive_transit_required(state)
    next_state = {
        **state,
        "sop_required": sop_required,
    }
    return {
        "sop_required": sop_required,
        "context_summary": _build_context_summary(next_state),
        "ready_for_planning": all_required_sop_completed(next_state),
        "current_step": "tool_result_merged",
    }


def router_warning_node(state: TripPlannerState) -> Dict[str, Any]:
    """Inject a corrective warning and send the flow back to the agent loop."""
    warning = state.get("router_warning") or _build_router_warning_message(state)
    return {
        "router_warning": warning,
        "context_summary": _build_context_summary({**state, "router_warning": warning}),
        "current_step": "router_warning",
    }


def forced_exit_with_best_effort_node(state: TripPlannerState) -> Dict[str, Any]:
    """Stop the loop after max retries and continue with the best available context."""
    reason = state.get("force_exit_reason") or _build_forced_exit_reason(state)
    return {
        "forced_exit": True,
        "force_exit_reason": reason,
        "ready_for_planning": True,
        "context_summary": _build_context_summary(
            {
                **state,
                "forced_exit": True,
                "force_exit_reason": reason,
            }
        ),
        "current_step": "forced_exit_with_best_effort",
    }


def plan_trip_node(state: TripPlannerState) -> Dict[str, Any]:
    """行程规划节点"""
    print("[GRAPH] 正在生成行程计划...")
    
    request = state["request"]
    gathered_context = _copy_gathered_context(state)
    context_summary = state.get("context_summary", "")
    attractions_data = state.get("attractions_data", "")
    weather_data = state.get("weather_data", "")
    hotel_data = state.get("hotel_data", "")
    inferred_preferences = state.get("inferred_preferences", "")

    planning_attractions, planning_local_events = _filter_planning_candidates(
        state,
        attractions=list(gathered_context.get("attractions") or []),
        local_events=list(gathered_context.get("local_events") or []),
    )

    if planning_attractions:
        attractions_data = json.dumps(planning_attractions, ensure_ascii=False, indent=2)
    if gathered_context.get("weather"):
        weather_data = json.dumps(gathered_context["weather"], ensure_ascii=False, indent=2)
    if gathered_context.get("hotels"):
        hotel_data = json.dumps(gathered_context["hotels"], ensure_ascii=False, indent=2)

    planner_local_events = [
        item
        for item in planning_local_events
        if isinstance(item, dict) and item.get("conflict_status") != "conflicting"
    ]
    if not planner_local_events:
        planner_local_events = list(planning_local_events)
    local_events_data = json.dumps(planner_local_events, ensure_ascii=False, indent=2)
    transit_evidence_data = json.dumps(gathered_context.get("transit_evidence") or [], ensure_ascii=False, indent=2)
    candidate_filter_notes_data = json.dumps(state.get("candidate_filter_notes") or [], ensure_ascii=False, indent=2)
    
    llm = create_llm()
    
    # 构建系统提示词
    system_prompt = """你是行程规划专家。请根据景点、天气和酒店信息，生成详细的旅行计划。

返回完整的JSON格式（不要分段）:
```json
{
  "city": "城市名称",
  "start_date": "YYYY-MM-DD",
  "end_date": "YYYY-MM-DD",
  "days": [
    {
      "date": "YYYY-MM-DD",
      "day_index": 0,
      "description": "第1天行程概述",
      "transportation": "交通方式",
      "accommodation": "住宿类型",
      "hotel": {
        "name": "酒店名称",
        "address": "酒店地址",
        "location": {"longitude": 116.397128, "latitude": 39.916527},
        "price_range": "300-500元",
        "rating": "4.5",
        "distance": "距离景点2公里",
        "type": "经济型酒店",
        "estimated_cost": 400
      },
      "attractions": [],
      "meals": [
        {"type": "breakfast", "name": "早餐推荐", "description": "早餐描述", "estimated_cost": 30},
        {"type": "lunch", "name": "午餐推荐", "description": "午餐描述", "estimated_cost": 50},
        {"type": "dinner", "name": "晚餐推荐", "description": "晚餐描述", "estimated_cost": 80}
      ]
    }
  ],
  "weather_info": [],
  "overall_suggestions": "总体建议",
  "budget": {
    "total_attractions": 180,
    "total_hotels": 1200,
    "total_meals": 480,
    "total_transportation": 200,
    "total": 2060
  }
}
```

重要要求：
1. 每天安排2-3个景点
2. 每天必须包含早中晚三餐
3. 每天推荐一个具体的酒店
4. 考虑景点之间的距离
5. 必须包含预算信息
6. 返回完整的JSON，不要省略任何部分
"""
    
    # 构建用户查询
    user_query = f"""请根据以下信息生成{request.city}的{request.travel_days}天旅行计划:

**基本信息:**
- 城市: {request.city}
- 日期: {request.start_date} 至 {request.end_date}
- 天数: {request.travel_days}天
- 交通方式: {request.transportation}
- 住宿: {request.accommodation}
- 偏好: {', '.join(request.preferences) if request.preferences else '无'}

**景点信息:**
{attractions_data}

**天气信息:**
{weather_data}

**酒店信息:**
{hotel_data}

**信息搜集摘要:**
{context_summary or '无'}

**本地活动信息:**
{local_events_data}

**交通测算证据:**
{transit_evidence_data}

**Candidate filter notes:**
{candidate_filter_notes_data}
"""

    user_query += (
        "\n**Local event usage rule:** treat local events as optional surprise candidates only. "
        "Prefer items where conflict_status is not conflicting, and do not let local events replace the core attraction plan."
    )

    if inferred_preferences:
        user_query += f"\n\n**历史偏好摘要（仅供参考，本次明确输入优先）:**\n{inferred_preferences}"
    
    if request.free_text_input:
        user_query += f"\n**额外要求:** {request.free_text_input}"
    
    # 调用LLM
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_query)
    ]
    
    response = llm.invoke(messages)
    final_plan_raw = response.content
    
    print(f"[GRAPH] 行程规划完成: {len(final_plan_raw)} 字符")
    
    return {
        "final_plan_raw": final_plan_raw,
        "current_step": "trip_planned"
    }


def error_handler_node(state: TripPlannerState) -> Dict[str, Any]:
    """错误处理节点"""
    print("[GRAPH] 发生错误，使用备用方案...")
    
    error = state.get("error", "Unknown error")
    print(f"错误信息: {error}")
    
    # 生成简单的备用计划
    request = state["request"]
    fallback_plan = {
        "city": request.city,
        "start_date": request.start_date,
        "end_date": request.end_date,
        "days": [],
        "weather_info": [],
        "overall_suggestions": f"由于技术问题，生成了简化版计划。建议访问官方旅游网站获取更多信息。"
    }
    
    return {
        "final_plan": fallback_plan,
        "current_step": "error_handled"
    }


def parse_plan_node(state: TripPlannerState) -> Dict[str, Any]:
    """解析节点：将 LLM 输出的字符串解析为结构化数据"""
    print("🔍 正在解析行程计划...")
    
    final_plan_raw = state.get("final_plan_raw", "")
    parse_retry_count = state.get("parse_retry_count", 0)
    
    if not final_plan_raw:
        print("[GRAPH] 未找到原始计划数据")
        return {
            "error": "No raw plan data found",
            "parse_retry_count": parse_retry_count + 1,
            "current_step": "parse_failed"
        }
    
    try:
        # 尝试从响应中提取 JSON
        if "```json" in final_plan_raw:
            json_start = final_plan_raw.find("```json") + 7
            json_end = final_plan_raw.find("```", json_start)
            json_str = final_plan_raw[json_start:json_end].strip()
        elif "```" in final_plan_raw:
            json_start = final_plan_raw.find("```") + 3
            json_end = final_plan_raw.find("```", json_start)
            json_str = final_plan_raw[json_start:json_end].strip()
        elif "{" in final_plan_raw and "}" in final_plan_raw:
            # 直接查找 JSON 对象
            json_start = final_plan_raw.find("{")
            json_end = final_plan_raw.rfind("}") + 1
            json_str = final_plan_raw[json_start:json_end]
        else:
            raise ValueError("响应中未找到 JSON 数据")
        
        # 解析 JSON
        final_plan = json.loads(json_str)
        
        print(f"[GRAPH] 解析成功: {final_plan.get('city', 'Unknown')} {len(final_plan.get('days', []))}天行程")
        
        return {
            "final_plan": final_plan,
            "parse_retry_count": 0,  # 解析成功，重置计数
            "current_step": "plan_parsed"
        }
        
    except Exception as e:
        print(f"[GRAPH] 解析失败: {str(e)}")
        return {
            "error": f"Parse error: {str(e)}",
            "parse_retry_count": parse_retry_count + 1,
            "current_step": "parse_failed"
        }


def schedule_plan_node(state: TripPlannerState) -> Dict[str, Any]:
    """对解析后的 plan 进行时间排程，填充景点时间和 timeline。"""
    print("[SCHEDULE] 正在生成可执行时间线...")

    final_plan = state.get("final_plan")
    request = state["request"]
    if not isinstance(final_plan, dict):
        return {
            "schedule_applied": False,
            "schedule_notes": ["排程跳过: final_plan 非结构化数据"],
            "days_to_reschedule": None,
            "current_step": "schedule_skipped"
        }

    schedule_retry_count = state.get("schedule_retry_count", 0)
    requested_indexes = state.get("days_to_reschedule")

    cfg = ScheduleConfig(
        daily_start_time=request.daily_start_time or "09:00",
        daily_end_time=request.daily_end_time or "21:00",
        min_rest_time=request.min_rest_time or 15,
        default_travel_minutes=20,
        route_type=_infer_route_type(request.transportation),
        city=request.city,
    )

    days = final_plan.get("days", [])
    if not isinstance(days, list):
        return {
            "schedule_applied": False,
            "schedule_notes": ["排程跳过: days 字段不是列表"],
            "days_to_reschedule": None,
            "current_step": "schedule_skipped"
        }

    if isinstance(requested_indexes, list) and requested_indexes:
        target_indexes = sorted(
            {
                idx
                for idx in requested_indexes
                if isinstance(idx, int) and 0 <= idx < len(days)
            }
        )
    else:
        target_indexes = list(range(len(days)))

    warnings: list[str] = []
    schedule_failed = False
    scheduled_days: list[Any] = list(days)

    if not target_indexes:
        return {
            "final_plan": final_plan,
            "schedule_applied": True,
            "schedule_retry_count": schedule_retry_count,
            "schedule_notes": [],
            "days_to_reschedule": None,
            "current_step": "plan_scheduled"
        }

    worker_count = max(1, min(4, len(target_indexes)))
    future_map: dict[Any, int] = {}
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        for idx in target_indexes:
            day = days[idx]
            if not isinstance(day, dict):
                warnings.append(f"第{idx + 1}天排程跳过: day 非字典结构")
                continue
            future = executor.submit(schedule_day_plan, day, cfg)
            future_map[future] = idx

        for future in as_completed(future_map):
            idx = future_map[future]
            try:
                scheduled_day, day_warnings = future.result()
                scheduled_days[idx] = scheduled_day
                warnings.extend([f"第{idx + 1}天: {warning}" for warning in day_warnings])
            except Exception as exc:
                schedule_failed = True
                warnings.append(f"第{idx + 1}天排程失败: {exc}")
                scheduled_days[idx] = days[idx]

    final_plan["days"] = scheduled_days
    if warnings:
        existing_warnings = final_plan.get("warnings")
        if not isinstance(existing_warnings, list):
            existing_warnings = []
        existing_warnings.extend([f"排程: {item}" for item in warnings])
        final_plan["warnings"] = _dedupe_text_list(existing_warnings)

    if warnings:
        print(f"[SCHEDULE] 排程完成，告警 {len(warnings)} 条")
    else:
        print("[SCHEDULE] 排程完成，无告警")

    return {
        "final_plan": final_plan,
        "schedule_applied": not schedule_failed,
        "schedule_retry_count": schedule_retry_count,
        "schedule_notes": warnings,
        "days_to_reschedule": None,
        "current_step": "plan_scheduled"
    }


def verify_plan_node(state: TripPlannerState) -> Dict[str, Any]:
    """校验节点：检查计划的完整性和合理性"""
    print("[GRAPH] 正在校验行程计划...")
    
    final_plan = state.get("final_plan")
    request = state["request"]
    violations = []
    
    if not final_plan:
        violations.append({
            "type": "missing_plan",
            "severity": "critical",
            "fixable": False,  # 数据为空无法修复，需重新生成
            "message": "计划数据为空"
        })
        return {
            "violations": violations,
            "verify_count": state.get("verify_count", 0) + 1,
            "current_step": "verify_failed"
        }
    
    # 检查必需字段
    required_fields = ["city", "start_date", "end_date", "days"]
    for field in required_fields:
        if field not in final_plan:
            violations.append({
                "type": "missing_field",
                "field": field,
                "severity": "critical",
                "fixable": field == "days",  # days 可以修复，其他关键字段不可修复
                "message": f"缺少必需字段: {field}"
            })
    
    # 检查天数是否匹配
    days = final_plan.get("days", [])
    if len(days) != request.travel_days:
        violations.append({
            "type": "days_mismatch",
            "severity": "critical",
            "fixable": True,  # 天数不匹配可以修复
            "message": f"计划天数 {len(days)} 与请求天数 {request.travel_days} 不匹配",
            "expected": request.travel_days,
            "actual": len(days)
        })
    
    # 检查每天的行程
    for i, day in enumerate(days):
        day_violations = []
        
        # 检查必需字段
        day_required = ["date", "day_index", "attractions", "meals"]
        for field in day_required:
            if field not in day:
                day_violations.append(f"缺少字段: {field}")
        
        # 检查景点数量
        attractions = day.get("attractions", [])
        if len(attractions) < 2:
            day_violations.append(f"景点数量不足 (至少需要2个，当前{len(attractions)}个)")
        
        # 检查餐食
        meals = day.get("meals", [])
        if len(meals) < 3:
            day_violations.append(f"餐食不完整 (需要早中晚3餐，当前{len(meals)}餐)")
        else:
            meal_types = {meal.get("type") for meal in meals}
            required_meal_types = {"breakfast", "lunch", "dinner"}
            missing_meals = required_meal_types - meal_types
            if missing_meals:
                day_violations.append(f"缺少餐食类型: {', '.join(missing_meals)}")
        
        # 检查景点信息完整性
        for j, attraction in enumerate(attractions):
            if "name" not in attraction:
                day_violations.append(f"景点{j+1}缺少名称")
            if "description" not in attraction:
                day_violations.append(f"景点{j+1}缺少描述信息")
            if "location" not in attraction:
                day_violations.append(f"景点{j+1}缺少位置信息")
            elif "longitude" not in attraction["location"] or "latitude" not in attraction["location"]:
                day_violations.append(f"景点{j+1}位置坐标不完整")
        
        if day_violations:
            violations.append({
                "type": "day_incomplete",
                "day_index": i,
                "severity": "high",
                "fixable": True,  # 每日行程不完整可以修复
                "message": f"第{i+1}天行程不完整",
                "details": day_violations
            })
    
    # 检查预算信息
    if "budget" not in final_plan:
        violations.append({
            "type": "missing_budget",
            "severity": "medium",
            "fixable": True,  # 预算信息可以补充
            "message": "缺少预算信息"
        })
    
    if violations:
        print(f"[GRAPH] 发现 {len(violations)} 个问题:")
        for v in violations:
            print(f"   - [{v['severity']}] {v['message']}")
        return {
            "violations": violations,
            "current_step": "verify_failed"
        }
    else:
        print("[GRAPH] 校验通过，计划完整")
        return {
            "violations": None,
            "current_step": "verify_passed"
        }


def _extract_json_object(text: str) -> dict[str, Any] | None:
    """从模型文本中提取 JSON 对象，提取失败时返回 None。"""
    if not text:
        return None
    try:
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.find("```", start)
            payload = text[start:end].strip()
        elif "```" in text:
            start = text.find("```") + 3
            end = text.find("```", start)
            payload = text[start:end].strip()
        elif "{" in text and "}" in text:
            start = text.find("{")
            end = text.rfind("}") + 1
            payload = text[start:end]
        else:
            return None
        data = json.loads(payload)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _build_fallback_day(request: Any, day_index: int) -> dict[str, Any]:
    """当局部修复失败时，构造最小可用的单天行程兜底结构。"""
    base_date = datetime.strptime(request.start_date, "%Y-%m-%d") + timedelta(days=day_index)
    date_str = base_date.strftime("%Y-%m-%d")
    city = request.city
    accommodation = request.accommodation
    return {
        "date": date_str,
        "day_index": day_index,
        "description": f"第{day_index + 1}天轻量行程（自动兜底）",
        "transportation": request.transportation,
        "accommodation": accommodation,
        "hotel": None if "无需住宿" in str(accommodation) else {
            "name": f"{city}标准{accommodation}",
            "address": f"{city}市区",
            "location": {"longitude": 0.0, "latitude": 0.0},
            "price_range": "",
            "rating": "",
            "distance": "",
            "type": accommodation,
            "estimated_cost": 0,
        },
        "attractions": [
            {
                "name": f"{city}核心景点A",
                "address": f"{city}市区",
                "location": {"longitude": 0.0, "latitude": 0.0},
                "visit_duration": 90,
                "description": "自动补全景点A",
                "category": "景点",
                "ticket_price": 0,
            },
            {
                "name": f"{city}核心景点B",
                "address": f"{city}市区",
                "location": {"longitude": 0.0, "latitude": 0.0},
                "visit_duration": 90,
                "description": "自动补全景点B",
                "category": "景点",
                "ticket_price": 0,
            },
        ],
        "meals": [
            {"type": "breakfast", "name": "早餐", "description": "自动补全早餐", "estimated_cost": 0},
            {"type": "lunch", "name": "午餐", "description": "自动补全午餐", "estimated_cost": 0},
            {"type": "dinner", "name": "晚餐", "description": "自动补全晚餐", "estimated_cost": 0},
        ],
    }


def _rebuild_budget(plan: dict[str, Any]) -> None:
    """根据当前日程重建预算汇总，避免缺失预算字段导致重复修复。"""
    days = plan.get("days")
    if not isinstance(days, list):
        return

    total_attractions = 0
    total_hotels = 0
    total_meals = 0
    total_transportation = 0

    for day in days:
        if not isinstance(day, dict):
            continue
        for attraction in day.get("attractions", []) or []:
            total_attractions += int(attraction.get("ticket_price", 0) or 0)
        for meal in day.get("meals", []) or []:
            total_meals += int(meal.get("estimated_cost", 0) or 0)
        hotel = day.get("hotel") or {}
        if isinstance(hotel, dict):
            total_hotels += int(hotel.get("estimated_cost", 0) or 0)
        for item in day.get("timeline", []) or []:
            if isinstance(item, dict) and item.get("activity_type") == "transport":
                total_transportation += int(item.get("cost", 0) or 0)

    plan["budget"] = {
        "total_attractions": total_attractions,
        "total_hotels": total_hotels,
        "total_meals": total_meals,
        "total_transportation": total_transportation,
        "total": total_attractions + total_hotels + total_meals + total_transportation,
    }


def _normalize_plan_days(plan: dict[str, Any], request: Any) -> None:
    """将 days 结构标准化为请求天数，优先减少全局重生。"""
    days = plan.get("days")
    if not isinstance(days, list):
        days = []
        plan["days"] = days

    if len(days) > request.travel_days:
        plan["days"] = days[:request.travel_days]
        days = plan["days"]

    while len(days) < request.travel_days:
        days.append(_build_fallback_day(request, len(days)))

    for idx, day in enumerate(days):
        if not isinstance(day, dict):
            days[idx] = _build_fallback_day(request, idx)
            continue
        day["day_index"] = idx
        if "date" not in day:
            base_date = datetime.strptime(request.start_date, "%Y-%m-%d") + timedelta(days=idx)
            day["date"] = base_date.strftime("%Y-%m-%d")


def _collect_failed_day_indexes(violations: list[dict[str, Any]], day_count: int) -> list[int]:
    """从校验结果中提取需要局部修复的天索引。"""
    indexes: set[int] = set()
    for violation in violations:
        idx = violation.get("day_index")
        if isinstance(idx, int) and 0 <= idx < day_count:
            indexes.add(idx)
    return sorted(indexes)


def fix_plan_node(state: TripPlannerState) -> Dict[str, Any]:
    """修复节点：仅修复失败天，避免整份计划全局回环。"""
    print("[GRAPH] 正在局部修复失败天...")

    violations = state.get("violations", []) or []
    final_plan = state.get("final_plan", {})
    request = state["request"]
    llm = create_llm()

    if not isinstance(final_plan, dict):
        return {
            "final_plan": final_plan,
            "verify_count": state.get("verify_count", 0) + 1,
            "days_to_reschedule": None,
            "current_step": "plan_fixed_skipped",
        }

    # 仅处理可修复的 critical/high 问题，避免无意义回环。
    fixable_issues = [
        v for v in violations
        if v.get("severity") in ["critical", "high"] and v.get("fixable", True)
    ]
    if not fixable_issues:
        print("[GRAPH] 没有可修复的问题，保持原计划")
        return {
            "final_plan": final_plan,
            "final_plan_raw": json.dumps(final_plan, ensure_ascii=False),
            "verify_count": state.get("verify_count", 0) + 1,
            "days_to_reschedule": None,
            "current_step": "plan_fixed_skipped",
        }

    working_plan = json.loads(json.dumps(final_plan, ensure_ascii=False))
    _normalize_plan_days(working_plan, request)
    day_count = len(working_plan.get("days", []) or [])
    failed_day_indexes = _collect_failed_day_indexes(fixable_issues, day_count)
    if not failed_day_indexes:
        failed_day_indexes = list(range(day_count))

    issues_text = []
    for i, issue in enumerate(fixable_issues):
        line = f"{i + 1}. {issue.get('message', '未知问题')}"
        if "expected" in issue:
            line += f" (期望: {issue.get('expected')}, 实际: {issue.get('actual')})"
        if issue.get("details"):
            details = "\n".join(f"   - {detail}" for detail in issue.get("details", []))
            line += f"\n   详细问题:\n{details}"
        issues_text.append(line)

    day_payload = [
        working_plan["days"][idx]
        for idx in failed_day_indexes
        if 0 <= idx < day_count
    ]
    issues_block = "\n".join(issues_text)
    hard_constraints_block = _build_hard_constraints_block(state)

    system_prompt = f"""{hard_constraints_block}

你是行程局部修复专家。你只能修复给定的失败天，不要重写整份计划。

任务要求：
1. 只输出需要替换的天，输出字段名必须是 patched_days。
2. 每个 patched_day 必须包含 day_index，且 day_index 不能越界。
3. 保持未失败天完全不变。
4. 必须修复以下问题：
{issues_block}

返回 JSON：
```json
{{
  "patched_days": [
    {{
      "day_index": 0,
      "date": "YYYY-MM-DD",
      "description": "...",
      "transportation": "...",
      "accommodation": "...",
      "hotel": {{...}},
      "attractions": [...],
      "meals": [...]
    }}
  ]
}}
```
"""

    user_query = (
        f"失败天索引: {failed_day_indexes}\n"
        f"仅修复这些天，其他天不要输出。\n"
        f"失败天原始数据:\n{json.dumps(day_payload, ensure_ascii=False, indent=2)}"
    )

    patched_indexes: list[int] = []
    try:
        response = llm.invoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_query),
            ]
        )
        payload = _extract_json_object(str(response.content))
        patched_days = payload.get("patched_days", []) if isinstance(payload, dict) else []

        if isinstance(patched_days, list):
            for item in patched_days:
                if not isinstance(item, dict):
                    continue
                idx = item.get("day_index")
                if not isinstance(idx, int) or idx < 0 or idx >= day_count:
                    continue
                item["day_index"] = idx
                working_plan["days"][idx] = item
                patched_indexes.append(idx)
    except Exception as exc:
        print(f"[GRAPH] 局部修复调用失败，进入兜底: {exc}")

    # 若模型未成功返回有效补丁，使用兜底填充失败天，确保不再整份回环。
    if not patched_indexes:
        for idx in failed_day_indexes:
            if 0 <= idx < day_count:
                working_plan["days"][idx] = _build_fallback_day(request, idx)
                patched_indexes.append(idx)

    _normalize_plan_days(working_plan, request)
    _rebuild_budget(working_plan)

    warnings = working_plan.get("warnings")
    if not isinstance(warnings, list):
        warnings = []
    warnings.append(f"局部修复: 已替换 {len(set(patched_indexes))} 天行程")
    working_plan["warnings"] = _dedupe_text_list(warnings)

    print(f"[GRAPH] 局部修复完成: 替换 {len(set(patched_indexes))} 天")

    return {
        "final_plan": working_plan,
        "final_plan_raw": json.dumps(working_plan, ensure_ascii=False),
        "days_to_reschedule": sorted(set(patched_indexes)),
        "verify_count": state.get("verify_count", 0) + 1,
        "current_step": "plan_fixed_partial",
    }


# ==================== 条件路由函数 ====================

def _infer_route_type(transportation: str | None) -> str:
    text = str(transportation or "").lower()
    if any(keyword in text for keyword in ["自驾", "开车", "驾车", "打车", "taxi", "car", "driving"]):
        return "driving"
    if any(keyword in text for keyword in ["公交", "地铁", "公共", "bus", "subway", "transit"]):
        return "transit"
    return "walking"


def _dedupe_text_list(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        text = str(item).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def info_gathering_router(state: TripPlannerState) -> str:
    if state.get("loop_count", 0) >= state.get("max_loops", 5):
        return "forced_exit_with_best_effort"

    output = state.get("agent_output") or {}
    action = output.get("action")
    tool_name = output.get("tool_name")

    if action == "call_tool":
        if tool_name in INFO_GATHERING_TOOL_NAMES:
            return str(tool_name)
        return "router_warning"

    if action == "submit_context":
        if all_required_sop_completed(state) and output.get("ready_for_planning") is True:
            return "plan_trip"
        return "router_warning"

    if action == "continue":
        if _missing_required_steps(state):
            return "router_warning"
        return "info_gathering_agent"

    return "router_warning"


def should_retry_parse(state: TripPlannerState) -> Literal["schedule_plan", "parse_plan", "error_handler"]:
    """决定解析后的下一步：成功→验证，失败→重试或错误处理"""
    # 解析成功，进入验证
    if state.get("current_step") == "plan_parsed":
        return "schedule_plan"
    
    # 解析失败，检查是否可以重试
    parse_retry_count = state.get("parse_retry_count", 0)
    MAX_PARSE_RETRIES = 3
    
    if parse_retry_count >= MAX_PARSE_RETRIES:
        print(f"[GRAPH] 解析重试次数已达上限 ({MAX_PARSE_RETRIES}), 进入错误处理")
        return "error_handler"
    
    print(f"[GRAPH] 重新尝试解析 (第 {parse_retry_count} 次/{MAX_PARSE_RETRIES})")
    return "parse_plan"


def should_fix_or_end(state: TripPlannerState) -> Literal["fix_plan", "END"]:
    """根据校验结果智能决定是修复还是结束"""
    violations = state.get("violations")
    verify_count = state.get("verify_count", 0)
    MAX_VERIFY_ATTEMPTS = 2  # 最多修复2次（初次验证+1次修复后验证）
    
    print(f"🔍 [DEBUG] violations={violations is not None}, verify_count={verify_count}")
    
    # 策略1: 无问题直接结束
    if not violations:
        print("[GRAPH] 校验通过，流程结束")
        return "END"
    
    print(f"🔍 [DEBUG] violations数量: {len(violations)}")
    
    # 策略2: 检查是否有不可修复的问题
    unfixable = [v for v in violations if not v.get("fixable", True)]
    if unfixable:
        print(f"[GRAPH] 发现 {len(unfixable)} 个不可修复问题，放弃修复")
        for v in unfixable:
            print(f"   - {v['message']}")
        return "END"
    
    # 策略3: 限制修复次数
    if verify_count >= MAX_VERIFY_ATTEMPTS:
        print(f"[GRAPH] 已尝试修复 {verify_count} 次，接受当前结果")
        return "END"
    
    # 策略4: 只修复 critical 或 high 级别且 fixable 的问题
    fixable_important = [
        v for v in violations 
        if v.get("severity") in ["critical", "high"] and v.get("fixable", True)
    ]
    
    print(f"🔍 [DEBUG] fixable_important数量: {len(fixable_important)}")
    for v in fixable_important:
        print(f"   - severity={v.get('severity')}, fixable={v.get('fixable')}, msg={v.get('message')}")
    
    # 策略5: 问题太多，放弃修复
    if len(fixable_important) > 3:
        print(f"[GRAPH] 可修复问题过多({len(fixable_important)}个)，接受当前结果")
        return "END"
    
    # 策略6: 有少量可修复的重要问题，尝试修复
    if len(fixable_important) > 0:
        print(f"[GRAPH] 发现 {len(fixable_important)} 个可修复的重要问题，尝试修复")
        for v in fixable_important:
            print(f"   - {v['message']}")
        return "fix_plan"
    
    # 策略7: 只有 medium/low 级别的问题，直接接受
    print(f"[GRAPH] 仅有轻微问题({len(violations)}个)，接受当前结果")
    return "END"
