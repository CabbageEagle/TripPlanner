"""Verification for the local-events capability wrapper."""

from __future__ import annotations

import json
import os
import sys
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

os.environ.setdefault("DEBUG", "false")

BACKEND_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.agents import graph_nodes as graph_nodes_module  # noqa: E402
from app.agents.graph_nodes import search_local_events_node  # noqa: E402
from app.agents.graph_nodes import plan_trip_node  # noqa: E402
from app.agents.tools import CAPABILITY_TOOLS, get_capability_tool  # noqa: E402
from app.agents.tools.local_events_tool import (  # noqa: E402
    SearchLocalEventsInput,
    search_local_events_tool,
)
from app.models.schemas import TripRequest  # noqa: E402
from app.services.local_events_service import LocalEventsService  # noqa: E402


class FakeLLMResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class FakeLLM:
    def __init__(self, content: str) -> None:
        self._content = content

    def invoke(self, _messages):
        return FakeLLMResponse(self._content)


class CapturingLLM:
    def __init__(self, content: str) -> None:
        self._content = content
        self.messages = None

    def invoke(self, messages):
        self.messages = messages
        return FakeLLMResponse(self._content)


class LocalEventsToolingTests(unittest.TestCase):
    def build_request(self) -> TripRequest:
        return TripRequest(
            city="上海",
            start_date="2026-04-20",
            end_date="2026-04-21",
            travel_days=2,
            transportation="公共交通",
            accommodation="经济型酒店",
            preferences=["美食"],
            free_text_input="希望安排得轻松一些",
        )

    def base_state(self) -> dict:
        return {
            "request": self.build_request(),
            "memory_summary": "用户过往偏好：展览、亲子活动",
            "base_constraints": {},
            "attractions_data": None,
            "weather_data": None,
            "hotel_data": None,
            "inferred_preferences": "展览, 亲子",
            "sop_required": {
                "weather_required": True,
                "attractions_required": True,
                "hotels_required": True,
                "transit_required": False,
                "local_events_optional": True,
            },
            "sop_completed": {
                "weather_done": True,
                "attractions_done": True,
                "hotels_done": True,
                "transit_done": False,
            },
            "gathered_context": {
                "attractions": [{"name": "spot-1"}, {"name": "spot-2"}, {"name": "spot-3"}, {"name": "spot-4"}],
                "weather": None,
                "hotels": [],
                "local_events": [],
                "transit_evidence": [],
            },
            "context_summary": "",
            "tool_call_history": [],
            "candidate_filter_notes": [],
            "agent_output": None,
            "ready_for_planning": False,
            "loop_count": 0,
            "max_loops": 5,
            "router_warning": None,
            "forced_exit": False,
            "force_exit_reason": None,
            "final_plan_raw": None,
            "final_plan": None,
            "violations": None,
            "verify_count": 0,
            "parse_retry_count": 0,
            "schedule_applied": False,
            "schedule_retry_count": 0,
            "schedule_notes": [],
            "days_to_reschedule": None,
            "current_step": "initialized",
            "error": None,
        }

    def test_search_local_events_input_rejects_empty_keywords(self):
        with self.assertRaises(ValidationError):
            SearchLocalEventsInput(
                city="上海",
                start_date="2026-04-20",
                end_date="2026-04-21",
                interest_keywords=[],
            )

    def test_search_local_events_input_rejects_invalid_date_range(self):
        with self.assertRaises(ValidationError):
            SearchLocalEventsInput(
                city="上海",
                start_date="2026-04-22",
                end_date="2026-04-21",
                interest_keywords=["展览"],
            )

    def test_tool_description_mentions_on_demand_and_conflict_check(self):
        description = getattr(search_local_events_tool, "description", "") or ""
        self.assertIn("按需触发", description)
        self.assertIn("惊喜感创造工具", description)
        self.assertIn("冲突", description)

    def test_registry_returns_search_local_events_tool(self):
        self.assertIs(get_capability_tool("search_local_events_tool"), CAPABILITY_TOOLS["search_local_events_tool"])

    def test_legacy_local_events_symbol_is_removed(self):
        self.assertFalse(hasattr(graph_nodes_module, "_legacy_search_local_events_node"))

    @patch(
        "app.services.local_events_service.create_local_events_llm",
        return_value=FakeLLM(
            json.dumps(
                [
                    {
                        "name": "过期展览",
                        "category": "展览",
                        "date": "2026-04-25",
                        "time_window": "10:00-12:00",
                        "address": "上海某展馆",
                        "description": "不在旅行日期内",
                        "interest_match_terms": ["展览"],
                    },
                    {
                        "name": "周末亲子市集",
                        "category": "亲子",
                        "date": "2026-04-20",
                        "time_window": "",
                        "address": "上海某公园",
                        "description": "适合带娃散步",
                        "interest_match_terms": ["亲子"],
                    },
                ],
                ensure_ascii=False,
            )
        ),
    )
    def test_service_marks_conflicting_and_unknown_statuses(self, _llm):
        service = LocalEventsService()
        result = service.search_local_events(
            city="上海",
            start_date="2026-04-20",
            end_date="2026-04-21",
            interest_keywords=["展览", "亲子"],
            daily_start_time="09:00",
            daily_end_time="21:00",
        )
        self.assertEqual(result["items"][0]["conflict_status"], "conflicting")
        self.assertEqual(result["items"][1]["conflict_status"], "unknown")

    def test_search_local_events_node_uses_memory_keywords_and_writes_items(self):
        state = self.base_state()
        captured: dict[str, object] = {}

        def fake_invoke(payload):
            captured["payload"] = payload
            return {
                "text": "Found 1 optional local event candidate.",
                "items": [
                    {
                        "name": "城市亲子展",
                        "category": "展览",
                        "date": "2026-04-20",
                        "time_window": "10:00-12:00",
                        "address": "上海展览中心",
                        "description": "适合亲子家庭",
                        "interest_match_terms": ["展览", "亲子"],
                        "conflict_status": "feasible",
                        "conflict_reason": "No obvious schedule conflict was detected.",
                    }
                ],
                "warning": None,
            }

        with patch("app.agents.graph_nodes._get_capability_tool", return_value=SimpleNamespace(invoke=fake_invoke)):
            result = search_local_events_node(state)

        payload = captured["payload"]
        self.assertIn("展览", payload["interest_keywords"])
        self.assertIn("亲子", payload["interest_keywords"])
        self.assertEqual(result["gathered_context"]["local_events"][0]["name"], "城市亲子展")
        self.assertEqual(result["tool_call_history"][-1]["tool_name"], "search_local_events_tool")

    def test_plan_trip_prefers_non_conflicting_local_events(self):
        state = self.base_state()
        state["gathered_context"]["local_events"] = [
            {
                "name": "冲突演出",
                "category": "演出",
                "date": "2026-04-20",
                "time_window": "23:00-23:30",
                "address": "上海剧场",
                "description": "很晚开始",
                "interest_match_terms": ["演出"],
                "conflict_status": "conflicting",
                "conflict_reason": "Outside daily schedule.",
            },
            {
                "name": "白天展览",
                "category": "展览",
                "date": "2026-04-20",
                "time_window": "10:00-12:00",
                "address": "上海展览馆",
                "description": "白天可插入",
                "interest_match_terms": ["展览"],
                "conflict_status": "feasible",
                "conflict_reason": "No obvious schedule conflict was detected.",
            },
        ]
        llm = CapturingLLM("{}")

        with patch("app.agents.graph_nodes.create_llm", return_value=llm):
            plan_trip_node(state)

        user_query = llm.messages[1].content
        self.assertIn("白天展览", user_query)
        self.assertNotIn("冲突演出", user_query)

    def test_plan_trip_falls_back_to_all_local_events_when_filtered_list_is_empty(self):
        state = self.base_state()
        state["gathered_context"]["local_events"] = [
            {
                "name": "仅冲突活动",
                "category": "演出",
                "date": "2026-04-20",
                "time_window": "23:00-23:30",
                "address": "上海剧场",
                "description": "唯一候选",
                "interest_match_terms": ["演出"],
                "conflict_status": "conflicting",
                "conflict_reason": "Outside daily schedule.",
            }
        ]
        llm = CapturingLLM("{}")

        with patch("app.agents.graph_nodes.create_llm", return_value=llm):
            plan_trip_node(state)

        user_query = llm.messages[1].content
        self.assertIn("仅冲突活动", user_query)


if __name__ == "__main__":
    unittest.main(verbosity=2)
