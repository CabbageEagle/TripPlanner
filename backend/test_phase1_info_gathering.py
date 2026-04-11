"""Minimal phase-1 verification for the info-gathering subgraph."""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("DEBUG", "false")

BACKEND_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.agents.graph_nodes import (  # noqa: E402
    forced_exit_with_best_effort_node,
    info_gathering_agent_node,
    info_gathering_router,
    init_info_gathering_node,
    query_weather_node,
    router_warning_node,
    search_hotels_node,
)
from app.models.schemas import TripRequest  # noqa: E402


class FakeLLMResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class FakeLLM:
    def __init__(self, content: str) -> None:
        self._content = content

    def invoke(self, _messages):
        return FakeLLMResponse(self._content)


class FakeAmapService:
    def get_weather(self, _city: str):
        return [
            {
                "date": "2026-04-20",
                "day_weather": "晴",
                "night_weather": "多云",
                "day_temp": 25,
                "night_temp": 18,
                "wind_direction": "东风",
                "wind_power": "3级",
            }
        ]

    def geocode(self, _address: str, city: str | None = None):
        return {
            "longitude": 121.47,
            "latitude": 31.23,
            "city": city,
        }


class InfoGatheringPhase1Tests(unittest.TestCase):
    def build_request(self, *, accommodation: str = "经济型酒店", free_text: str = "") -> TripRequest:
        return TripRequest(
            city="上海",
            start_date="2026-04-20",
            end_date="2026-04-20",
            travel_days=1,
            transportation="公共交通",
            accommodation=accommodation,
            preferences=["美食", "城市漫步"],
            free_text_input=free_text,
        )

    def base_state(self, *, accommodation: str = "经济型酒店", free_text: str = "") -> dict:
        request = self.build_request(accommodation=accommodation, free_text=free_text)
        state = {
            "request": request,
            "memory_summary": "",
            "base_constraints": {},
            "attractions_data": None,
            "weather_data": None,
            "hotel_data": None,
            "inferred_preferences": None,
            "sop_required": {
                "weather_required": True,
                "attractions_required": True,
                "hotels_required": accommodation not in {"无需住宿", "无须住宿", "不住宿"},
                "transit_required": False,
                "local_events_optional": False,
            },
            "sop_completed": {
                "weather_done": False,
                "attractions_done": False,
                "hotels_done": False,
                "transit_done": False,
            },
            "gathered_context": {
                "attractions": [],
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
        return state

    def test_init_info_gathering_sets_structured_defaults(self):
        state = self.base_state(accommodation="无需住宿", free_text="轻松一点，少折腾")
        result = init_info_gathering_node(state)
        self.assertIn("sop_required", result)
        self.assertFalse(result["sop_required"]["hotels_required"])
        self.assertTrue(result["sop_required"]["transit_required"])
        self.assertEqual(result["loop_count"], 0)
        self.assertEqual(result["max_loops"], 5)

    def test_router_warning_blocks_early_submit_with_specific_reason(self):
        state = self.base_state()
        state["agent_output"] = {
            "action": "submit_context",
            "tool_name": None,
            "tool_input": {},
            "reasoning_summary": "done",
            "ready_for_planning": True,
            "checklist_update": {
                "weather_done": False,
                "attractions_done": True,
                "hotels_done": False,
                "transit_done": False,
            },
        }
        routed = info_gathering_router(state)
        warned = router_warning_node(state)
        self.assertEqual(routed, "router_warning")
        self.assertIn("天气信息尚未完成", warned["router_warning"])
        self.assertIn("酒店信息尚未完成", warned["router_warning"])

    def test_forced_exit_reason_contains_missing_steps_and_history(self):
        state = self.base_state()
        state["loop_count"] = 5
        state["max_loops"] = 5
        state["tool_call_history"] = [
            {"tool_name": "search_attractions_tool"},
            {"tool_name": "query_weather_tool"},
        ]
        result = forced_exit_with_best_effort_node(state)
        self.assertTrue(result["forced_exit"])
        self.assertIn("5/5", result["force_exit_reason"])
        self.assertIn("景点信息尚未完成", result["force_exit_reason"])
        self.assertIn("search_attractions_tool", result["force_exit_reason"])

    @patch("app.agents.graph_nodes.get_amap_service", return_value=FakeAmapService())
    def test_query_weather_updates_sop_and_tool_history(self, _amap):
        state = self.base_state()
        result = query_weather_node(state)
        self.assertTrue(result["sop_completed"]["weather_done"])
        self.assertEqual(result["tool_call_history"][-1]["tool_name"], "query_weather_tool")
        self.assertEqual(json.loads(result["weather_data"])[0]["day_weather"], "晴")

    @patch(
        "app.agents.graph_nodes.create_llm",
        return_value=FakeLLM(
            json.dumps(
                [
                    {
                        "name": "静安酒店",
                        "address": "上海市静安区测试路 1 号",
                        "price_range": "300-500元",
                        "rating": "4.5",
                        "distance": "距离核心景点2公里",
                        "type": "经济型酒店",
                        "estimated_cost": 400,
                    }
                ],
                ensure_ascii=False,
            )
        ),
    )
    @patch("app.agents.graph_nodes.get_amap_service", return_value=FakeAmapService())
    def test_search_hotels_updates_sop_and_tool_history(self, _amap, _llm):
        state = self.base_state()
        result = search_hotels_node(state)
        self.assertTrue(result["sop_completed"]["hotels_done"])
        self.assertEqual(result["tool_call_history"][-1]["tool_name"], "search_hotels_tool")
        self.assertEqual(json.loads(result["hotel_data"])[0]["name"], "静安酒店")

    def test_info_gathering_agent_selects_required_tool_first(self):
        state = self.base_state()
        result = info_gathering_agent_node(state)
        self.assertEqual(result["agent_output"]["action"], "call_tool")
        self.assertEqual(result["agent_output"]["tool_name"], "search_attractions_tool")

    def test_info_gathering_agent_triggers_local_events_for_keyword_hit(self):
        state = self.base_state(free_text="想看演出和音乐会")
        state["sop_completed"].update(
            {
                "weather_done": True,
                "attractions_done": True,
                "hotels_done": True,
                "transit_done": False,
            }
        )
        state["gathered_context"]["attractions"] = [{"name": f"spot-{idx}"} for idx in range(4)]
        result = info_gathering_agent_node(state)
        self.assertEqual(result["agent_output"]["action"], "call_tool")
        self.assertEqual(result["agent_output"]["tool_name"], "search_local_events_tool")

    def test_info_gathering_agent_triggers_local_events_when_attractions_are_insufficient(self):
        state = self.base_state(accommodation="无需住宿")
        state["sop_required"]["hotels_required"] = False
        state["sop_completed"].update(
            {
                "weather_done": True,
                "attractions_done": True,
                "hotels_done": False,
                "transit_done": False,
            }
        )
        state["gathered_context"]["attractions"] = [{"name": "spot-1"}]
        result = info_gathering_agent_node(state)
        self.assertEqual(result["agent_output"]["action"], "call_tool")
        self.assertEqual(result["agent_output"]["tool_name"], "search_local_events_tool")


if __name__ == "__main__":
    unittest.main(verbosity=2)
