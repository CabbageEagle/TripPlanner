"""Verification for phase-3 transit gating and candidate filtering."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("DEBUG", "false")

BACKEND_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.agents.graph_nodes import (  # noqa: E402
    estimate_transit_time_node,
    info_gathering_agent_node,
    merge_tool_result_node,
    plan_trip_node,
)
from app.agents.tools import get_capability_tool  # noqa: E402
from app.models.schemas import TripRequest  # noqa: E402


class FakeAmapService:
    def __init__(self, *, duration: int = 70) -> None:
        self.duration = duration

    def plan_route(
        self,
        origin_address: str,
        destination_address: str,
        origin_city: str | None = None,
        destination_city: str | None = None,
        route_type: str = "transit",
    ):
        return {
            "distance": 12.0,
            "duration": self.duration,
            "route_type": route_type,
            "description": f"{route_type} route from {origin_address} to {destination_address}",
        }


class CapturingLLMResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class CapturingLLM:
    def __init__(self, content: str = "{}") -> None:
        self.content = content
        self.messages = None

    def invoke(self, messages):
        self.messages = messages
        return CapturingLLMResponse(self.content)


class TransitPhase3Tests(unittest.TestCase):
    def build_request(self, *, free_text: str = "") -> TripRequest:
        return TripRequest(
            city="上海",
            start_date="2026-04-20",
            end_date="2026-04-20",
            travel_days=1,
            transportation="公共交通",
            accommodation="经济型酒店",
            preferences=["展览", "城市漫步"],
            free_text_input=free_text,
        )

    def base_state(self, *, free_text: str = "") -> dict:
        request = self.build_request(free_text=free_text)
        return {
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
                "hotels_required": True,
                "transit_required": False,
                "local_events_optional": False,
            },
            "sop_completed": {
                "weather_done": True,
                "attractions_done": True,
                "hotels_done": True,
                "transit_done": False,
            },
            "gathered_context": {
                "attractions": [
                    {"name": "Bund", "address": "黄浦区中山东一路1号"},
                    {"name": "Museum", "address": "浦东新区世纪大道100号"},
                    {"name": "Gallery", "address": "徐汇区复兴中路10号"},
                    {"name": "Park", "address": "静安区南京西路200号"},
                ],
                "weather": None,
                "hotels": [
                    {"name": "Jingan Hotel", "address": "静安区北京西路1号"},
                ],
                "local_events": [],
                "transit_evidence": [],
            },
            "context_summary": "",
            "last_tool_result": None,
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

    def test_registry_returns_transit_tool(self):
        self.assertIsNotNone(get_capability_tool("estimate_transit_time_tool"))

    def test_merge_marks_transit_required_for_fixed_time_local_event(self):
        state = self.base_state()
        state["gathered_context"]["local_events"] = [
            {
                "name": "Night Concert",
                "category": "演出",
                "date": "2026-04-20",
                "time_window": "19:00-21:00",
                "address": "黄浦区延安东路1号",
                "description": "Evening show",
                "interest_match_terms": ["演出"],
                "conflict_status": "feasible",
                "conflict_reason": "No obvious schedule conflict was detected.",
            }
        ]
        result = merge_tool_result_node(state)
        self.assertTrue(result["sop_required"]["transit_required"])

    @patch("app.agents.tools.transit_tool.get_amap_service", return_value=FakeAmapService(duration=70))
    def test_estimate_transit_time_builds_drop_evidence_and_notes(self, _amap):
        state = self.base_state(free_text="尽量轻松一些，不折腾")
        state["gathered_context"]["local_events"] = [
            {
                "name": "Night Concert",
                "category": "演出",
                "date": "2026-04-20",
                "time_window": "19:00-21:00",
                "address": "黄浦区延安东路1号",
                "description": "Evening show",
                "interest_match_terms": ["演出"],
                "conflict_status": "feasible",
                "conflict_reason": "No obvious schedule conflict was detected.",
            }
        ]
        tool_result = estimate_transit_time_node(state)
        result = merge_tool_result_node({**state, **tool_result})
        self.assertTrue(result["sop_completed"]["transit_done"])
        self.assertEqual(result["gathered_context"]["transit_evidence"][0]["decision"], "drop_candidate")
        self.assertTrue(result["candidate_filter_notes"])

    def test_info_agent_selects_transit_tool_when_fixed_time_event_exists(self):
        state = self.base_state()
        state["gathered_context"]["local_events"] = [
            {
                "name": "Night Concert",
                "category": "演出",
                "date": "2026-04-20",
                "time_window": "19:00-21:00",
                "address": "黄浦区延安东路1号",
                "description": "Evening show",
                "interest_match_terms": ["演出"],
                "conflict_status": "feasible",
                "conflict_reason": "No obvious schedule conflict was detected.",
            }
        ]
        merged = merge_tool_result_node(state)
        next_state = {**state, **merged}
        result = info_gathering_agent_node(next_state)
        self.assertEqual(result["agent_output"]["tool_name"], "estimate_transit_time_tool")

    def test_plan_trip_filters_dropped_attraction_from_prompt(self):
        state = self.base_state()
        state["gathered_context"]["transit_evidence"] = [
            {
                "origin_name": "Bund",
                "destination_name": "Museum",
                "duration_minutes": 75,
                "decision": "drop_candidate",
                "reason": "Travel time too long for same-day plan",
            }
        ]
        state["candidate_filter_notes"] = ["Bund -> Museum 通勤 75 分钟，建议从同日候选中剔除。"]
        llm = CapturingLLM()

        with patch("app.agents.graph_nodes.create_llm", return_value=llm):
            plan_trip_node(state)

        user_query = llm.messages[1].content
        self.assertNotIn('"name": "Museum"', user_query)
        self.assertIn("Bund -> Museum", user_query)

    def test_plan_trip_filters_dropped_local_event_from_prompt(self):
        state = self.base_state()
        state["gathered_context"]["local_events"] = [
            {
                "name": "Night Concert",
                "category": "演出",
                "date": "2026-04-20",
                "time_window": "19:00-21:00",
                "address": "黄浦区延安东路1号",
                "description": "Evening show",
                "interest_match_terms": ["演出"],
                "conflict_status": "feasible",
                "conflict_reason": "No obvious schedule conflict was detected.",
            },
            {
                "name": "Day Exhibition",
                "category": "展览",
                "date": "2026-04-20",
                "time_window": "10:00-12:00",
                "address": "徐汇区复兴中路10号",
                "description": "Daytime exhibition",
                "interest_match_terms": ["展览"],
                "conflict_status": "feasible",
                "conflict_reason": "No obvious schedule conflict was detected.",
            },
        ]
        state["gathered_context"]["transit_evidence"] = [
            {
                "origin_name": "Bund",
                "destination_name": "Night Concert",
                "duration_minutes": 75,
                "decision": "drop_candidate",
                "reason": "Travel time too long for same-day plan",
            }
        ]
        llm = CapturingLLM()

        with patch("app.agents.graph_nodes.create_llm", return_value=llm):
            plan_trip_node(state)

        user_query = llm.messages[1].content
        self.assertNotIn('"name": "Night Concert"', user_query)
        self.assertIn("Day Exhibition", user_query)


if __name__ == "__main__":
    unittest.main(verbosity=2)
