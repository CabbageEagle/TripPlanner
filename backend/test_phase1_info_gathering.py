"""Minimal phase-1 verification for the info-gathering subgraph."""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("DEBUG", "false")

BACKEND_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.agents.graph_nodes import (  # noqa: E402
    _build_info_gathering_decision_prompt,
    build_agent_diagnostics,
    forced_exit_with_best_effort_node,
    info_gathering_agent_node,
    info_gathering_router,
    init_info_gathering_node,
    merge_tool_result_node,
    normalize_trip_plan_payload,
    query_weather_node,
    router_warning_node,
    search_attractions_node,
    search_hotels_node,
    sop_bootstrap_node,
)
from app.agents.tools import get_capability_tool  # noqa: E402
from app.services.amap_service import _extract_poi_list  # noqa: E402
from app.models.schemas import TripPlan, TripRequest  # noqa: E402


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

    def search_poi(self, keyword: str, _city: str, citylimit: bool = True):
        if "酒店" not in keyword and "hotel" not in keyword.lower():
            return [
                {
                    "id": "spot-1",
                    "name": "外滩",
                    "address": "上海市黄浦区中山东一路",
                    "location": {"longitude": 121.49, "latitude": 31.24},
                    "type": "景点",
                }
            ]
        return [
            {
                "id": "hotel-1",
                "name": "静安酒店",
                "address": "上海市静安区测试路 1 号",
                "location": {"longitude": 121.47, "latitude": 31.23},
                "type": "经济型酒店",
                "rating": "4.5",
            }
        ]


class EmptyAmapService(FakeAmapService):
    def get_weather(self, _city: str):
        return []

    def search_poi(self, _keyword: str, _city: str, citylimit: bool = True):
        return []


class MultiKeywordAmapService(FakeAmapService):
    def __init__(self) -> None:
        self.queries: list[str] = []

    def search_poi_with_raw(self, keyword: str, _city: str, citylimit: bool = True):
        self.queries.append(keyword)
        if "博物馆" not in keyword:
            return [], f"raw empty for {keyword}"
        return [
            {
                "id": "museum-1",
                "name": "城市博物馆",
                "address": "测试路 1 号",
                "location": {"longitude": 121.49, "latitude": 31.24},
                "type": "博物馆",
            }
        ], None


class RawFailureAmapService(FakeAmapService):
    def search_poi_with_raw(self, keyword: str, _city: str, citylimit: bool = True):
        return [], f"raw failure for {keyword}: MCP disconnected"


class HotelKeywordAmapService(FakeAmapService):
    def __init__(self) -> None:
        self.queries: list[str] = []

    def search_poi_with_raw(self, keyword: str, _city: str, citylimit: bool = True):
        self.queries.append(keyword)
        if keyword != "商务酒店":
            return [], f"raw empty for {keyword}"
        return [
            {
                "id": "hotel-business-1",
                "name": "商务酒店",
                "address": "测试路 2 号",
                "location": {"longitude": 121.47, "latitude": 31.23},
                "type": "酒店",
                "rating": "4.6",
            }
        ], None


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
        return state

    def test_init_info_gathering_sets_structured_defaults(self):
        state = self.base_state(accommodation="无需住宿", free_text="轻松一点，少折腾")
        result = init_info_gathering_node(state)
        self.assertIn("sop_required", result)
        self.assertFalse(result["sop_required"]["hotels_required"])
        self.assertTrue(result["sop_required"]["transit_required"])
        self.assertEqual(result["loop_count"], 0)
        self.assertEqual(result["max_loops"], 5)

    @patch("app.agents.graph_nodes.get_settings", return_value=SimpleNamespace(info_gathering_use_llm=False))
    def test_no_stay_accommodation_skips_hotel_sop(self, _settings):
        state = self.base_state(accommodation="不住宿（当天往返）")
        result = init_info_gathering_node(state)
        self.assertFalse(result["sop_required"]["hotels_required"])

        state.update(result)
        state["sop_completed"].update(
            {
                "weather_done": True,
                "attractions_done": True,
                "hotels_done": False,
                "transit_done": True,
            }
        )
        state["gathered_context"]["attractions"] = [{"name": f"spot-{idx}"} for idx in range(4)]
        decision = info_gathering_agent_node(state)
        self.assertNotEqual(decision["agent_output"]["tool_name"], "search_hotels_tool")

    def test_normalize_trip_plan_payload_makes_llm_plan_schema_compatible(self):
        request = self.build_request(accommodation="不住宿（当天往返）")
        raw_plan = {
            "days": [
                {
                    "attractions": [
                        {
                            "name": "外滩",
                            "location": {"lng": "121.49", "lat": "31.24"},
                            "rating": "",
                        }
                    ],
                    "meals": [{"type": "breakfast", "name": "早餐"}],
                    "hotel": {"name": "模型误填酒店"},
                }
            ],
            "warnings": "模型输出字段不完整",
        }
        normalized = normalize_trip_plan_payload(raw_plan, request)
        trip_plan = TripPlan(**normalized)

        self.assertEqual(trip_plan.city, request.city)
        self.assertIsNone(trip_plan.days[0].hotel)
        self.assertEqual(trip_plan.budget.total_hotels, 0)
        self.assertEqual(trip_plan.days[0].attractions[0].visit_duration, 90)
        self.assertEqual(trip_plan.days[0].attractions[0].location.longitude, 121.49)

    def test_normalize_trip_plan_payload_prefers_tool_weather(self):
        request = self.build_request()
        raw_plan = {
            "days": [],
            "weather_info": [{"date": request.start_date, "day_weather": "多云"}],
        }
        tool_weather = [
            {
                "date": request.start_date,
                "day_weather": "雷阵雨",
                "night_weather": "雷阵雨",
                "day_temp": 28,
                "night_temp": 19,
                "wind_direction": "北",
                "wind_power": "1-3",
            }
        ]
        normalized = normalize_trip_plan_payload(raw_plan, request, tool_weather)
        trip_plan = TripPlan(**normalized)
        self.assertEqual(trip_plan.weather_info[0].day_weather, "雷阵雨")
        self.assertEqual(trip_plan.weather_info[0].day_temp, 28)
        self.assertEqual(trip_plan.weather_info[0].night_temp, 19)

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

    @patch("app.agents.tools.weather_tool.get_amap_service", return_value=FakeAmapService())
    def test_query_weather_updates_sop_and_tool_history(self, _amap):
        state = self.base_state()
        tool_result = query_weather_node(state)
        self.assertIn("last_tool_result", tool_result)
        self.assertNotIn("tool_call_history", tool_result)
        result = merge_tool_result_node({**state, **tool_result})
        self.assertTrue(result["sop_completed"]["weather_done"])
        self.assertEqual(result["tool_call_history"][-1]["tool_name"], "query_weather_tool")
        self.assertEqual(json.loads(result["weather_data"])[0]["day_weather"], "晴")

    @patch("app.agents.tools.hotels_tool.get_amap_service", return_value=FakeAmapService())
    def test_search_hotels_updates_sop_and_tool_history(self, _amap):
        state = self.base_state()
        tool_result = search_hotels_node(state)
        result = merge_tool_result_node({**state, **tool_result})
        self.assertTrue(result["sop_completed"]["hotels_done"])
        self.assertEqual(result["tool_call_history"][-1]["tool_name"], "search_hotels_tool")
        self.assertEqual(json.loads(result["hotel_data"])[0]["name"], "静安酒店")

    def test_info_gathering_agent_selects_required_tool_first(self):
        state = self.base_state()
        result = info_gathering_agent_node(state)
        self.assertEqual(result["agent_output"]["action"], "call_tool")
        self.assertEqual(result["agent_output"]["tool_name"], "search_attractions_tool")

    @patch("app.agents.graph_nodes.get_settings", return_value=SimpleNamespace(info_gathering_use_llm=False))
    def test_info_gathering_does_not_repeat_failed_required_tool(self, _settings):
        state = self.base_state()
        state["tool_call_history"] = [
            {
                "tool_name": "search_attractions_tool",
                "success": False,
                "warning": "AMap returned no attraction candidates.",
            }
        ]
        result = info_gathering_agent_node(state)
        self.assertEqual(result["agent_output"]["tool_name"], "query_weather_tool")

        state["sop_completed"]["weather_done"] = True
        state["sop_completed"]["hotels_done"] = True
        state["sop_required"]["hotels_required"] = True
        result = info_gathering_agent_node(state)
        self.assertIsNone(result["agent_output"]["tool_name"])
        self.assertIn("force_exit_reason", result)

    def test_registry_returns_weather_and_hotels_tools(self):
        self.assertIsNotNone(get_capability_tool("search_attractions_tool"))
        self.assertIsNotNone(get_capability_tool("query_weather_tool"))
        self.assertIsNotNone(get_capability_tool("search_hotels_tool"))

    @patch("app.agents.tools.attractions_tool.get_amap_service")
    def test_search_attractions_uses_multiple_keywords(self, _amap):
        service = MultiKeywordAmapService()
        _amap.return_value = service
        result = get_capability_tool("search_attractions_tool").invoke(
            {"city": "上海", "keywords": ["历史文化"]}
        )
        self.assertEqual(len(result["items"]), 1)
        self.assertGreater(len(service.queries), 1)
        self.assertIn("博物馆", service.queries)

    @patch("app.agents.tools.attractions_tool.get_amap_service", return_value=RawFailureAmapService())
    def test_search_attractions_warning_contains_raw_failure(self, _amap):
        result = get_capability_tool("search_attractions_tool").invoke(
            {"city": "上海", "keywords": ["历史文化"]}
        )
        self.assertEqual(result["items"], [])
        self.assertIn("raw failure", result["warning"])
        self.assertIn("MCP disconnected", result["warning"])

    @patch("app.agents.tools.attractions_tool.get_amap_service", return_value=RawFailureAmapService())
    def test_search_attractions_normalizes_shopping_keyword(self, _amap):
        result = get_capability_tool("search_attractions_tool").invoke(
            {"city": "深圳", "keywords": ["购物"]}
        )
        search_keywords = result["meta"]["search_keywords"]
        self.assertNotIn("购物", search_keywords)
        self.assertIn("商业中心", search_keywords)
        self.assertIn("购物中心", search_keywords)

    @patch("app.agents.tools.hotels_tool.get_amap_service")
    def test_search_hotels_normalizes_comfort_preference(self, _amap):
        service = HotelKeywordAmapService()
        _amap.return_value = service
        result = get_capability_tool("search_hotels_tool").invoke(
            {"city": "深圳", "accommodation": "舒适型酒店"}
        )
        search_keywords = result["meta"]["search_keywords"]
        self.assertNotIn("舒适型酒店", search_keywords)
        self.assertIn("酒店", search_keywords)
        self.assertIn("宾馆", search_keywords)
        self.assertIn("商务酒店", search_keywords)
        self.assertEqual(len(result["items"]), 1)

    def test_extract_poi_list_keeps_raw_pois_without_location(self):
        payload = {
            "suggestion": {"keywords": [], "cities": []},
            "pois": [
                {
                    "id": "B02F306L5G",
                    "name": "莲花山公园",
                    "address": "深圳市福田区",
                }
            ],
        }
        pois = _extract_poi_list(payload)
        self.assertEqual(len(pois), 1)
        self.assertEqual(pois[0].name, "莲花山公园")
        self.assertEqual(pois[0].location.longitude, 0.0)

    @patch("app.agents.tools.attractions_tool.get_amap_service", return_value=FakeAmapService())
    @patch("app.agents.tools.weather_tool.get_amap_service", return_value=FakeAmapService())
    @patch("app.agents.tools.hotels_tool.get_amap_service", return_value=FakeAmapService())
    def test_sop_bootstrap_runs_base_required_tools_without_llm_loop(self, _hotels, _weather, _attractions):
        state = self.base_state()
        result = sop_bootstrap_node(state)
        self.assertTrue(result["sop_completed"]["attractions_done"])
        self.assertTrue(result["sop_completed"]["weather_done"])
        self.assertTrue(result["sop_completed"]["hotels_done"])
        self.assertEqual(result["loop_count"] if "loop_count" in result else state["loop_count"], 0)
        self.assertEqual(
            [record["tool_name"] for record in result["tool_call_history"]],
            ["search_attractions_tool", "query_weather_tool", "search_hotels_tool"],
        )
        self.assertIn("SOP bootstrap", result["tool_call_history"][0]["reason"])

    @patch("app.agents.tools.attractions_tool.get_amap_service", return_value=FakeAmapService())
    @patch("app.agents.tools.weather_tool.get_amap_service", return_value=FakeAmapService())
    @patch("app.agents.tools.hotels_tool.get_amap_service", side_effect=AssertionError("Hotels should be skipped"))
    def test_sop_bootstrap_skips_hotels_for_no_stay(self, _hotels, _weather, _attractions):
        state = self.base_state(accommodation="不住宿（当天往返）")
        state.update(init_info_gathering_node(state))
        result = sop_bootstrap_node(state)
        self.assertTrue(result["sop_completed"]["attractions_done"])
        self.assertTrue(result["sop_completed"]["weather_done"])
        self.assertFalse(result["sop_required"]["hotels_required"])
        self.assertNotIn(
            "search_hotels_tool",
            [record["tool_name"] for record in result["tool_call_history"]],
        )

    def test_info_gathering_prompt_contains_tool_guidance(self):
        state = self.base_state()
        messages = _build_info_gathering_decision_prompt(state)
        system_prompt = messages[0].content
        self.assertIn("real AMap POI data", system_prompt)
        self.assertIn("real AMap weather data", system_prompt)
        self.assertIn("cannot_be_replaced_by", system_prompt)
        self.assertIn("invent_weather", system_prompt)
        self.assertIn("invent_hotels", system_prompt)
        self.assertIn("required SOP complete", system_prompt)

    @patch("app.agents.tools.attractions_tool.get_amap_service", return_value=FakeAmapService())
    def test_search_attractions_updates_sop_and_tool_history(self, _amap):
        state = self.base_state()
        state["agent_output"] = {
            "action": "call_tool",
            "tool_name": "search_attractions_tool",
            "tool_input": {},
            "reasoning_summary": "Need baseline attractions before planning.",
            "ready_for_planning": False,
            "checklist_update": {
                "weather_done": False,
                "attractions_done": False,
                "hotels_done": False,
                "transit_done": False,
            },
        }
        tool_result = search_attractions_node(state)
        result = merge_tool_result_node({**state, **tool_result})
        self.assertTrue(result["sop_completed"]["attractions_done"])
        self.assertEqual(result["tool_call_history"][-1]["tool_name"], "search_attractions_tool")
        self.assertIn("baseline attractions", result["tool_call_history"][-1]["reason"])
        self.assertEqual(json.loads(result["attractions_data"])[0]["name"], "外滩")

    def test_build_agent_diagnostics_exposes_existing_state(self):
        state = self.base_state(free_text="想看展，行程轻松一点")
        state["sop_completed"] = {
            "weather_done": True,
            "attractions_done": True,
            "hotels_done": False,
            "transit_done": True,
        }
        state["sop_required"] = {
            "weather_required": True,
            "attractions_required": True,
            "hotels_required": False,
            "transit_required": True,
            "local_events_optional": True,
        }
        state["gathered_context"]["transit_evidence"] = [
            {
                "origin_name": "酒店",
                "destination_name": "远郊活动",
                "duration_minutes": 95,
                "decision": "drop_candidate",
                "reason": "exceeds threshold",
            }
        ]
        state["candidate_filter_notes"] = ["酒店 -> 远郊活动 通勤 95 分钟，建议从同日候选中剔除。"]
        state["tool_call_history"] = [
            {
                "tool_name": "estimate_transit_time_tool",
                "tool_input": {},
                "success": True,
                "reason": "Need transit evidence before submitting context.",
                "summary": "Collected 1 transit evidence items.",
                "result_count": 1,
            },
            {
                "tool_name": "search_local_events_tool",
                "tool_input": {},
                "success": False,
                "reason": "Optional local events may improve the itinerary.",
                "summary": "Local events lookup failed.",
                "result_count": 0,
                "warning": "search_local_events_tool failed",
            },
        ]
        state["router_warning"] = "仍有必查项未完成。"
        diagnostics = build_agent_diagnostics(state)
        self.assertTrue(diagnostics["sop_required"]["transit_required"])
        self.assertEqual(len(diagnostics["tool_calls"]), 2)
        self.assertEqual(len(diagnostics["tool_failures"]), 1)
        self.assertEqual(diagnostics["router_warning"], "仍有必查项未完成。")
        self.assertEqual(diagnostics["transit_filtered_candidates"][0]["destination_name"], "远郊活动")
        self.assertEqual(diagnostics["local_events"]["status"], "triggered")

    @patch("app.agents.graph_nodes.get_settings", return_value=SimpleNamespace(info_gathering_use_llm=True))
    @patch(
        "app.agents.graph_nodes.create_llm",
        return_value=FakeLLM(
            json.dumps(
                {
                    "action": "call_tool",
                    "tool_name": "query_weather_tool",
                    "reasoning_summary": "Need weather after attractions are ready.",
                    "ready_for_planning": False,
                },
                ensure_ascii=False,
            )
        ),
    )
    def test_info_gathering_llm_decision_selects_weather_when_allowed(self, _llm, _settings):
        state = self.base_state()
        state["sop_completed"]["attractions_done"] = True
        result = info_gathering_agent_node(state)
        self.assertEqual(result["agent_output"]["action"], "call_tool")
        self.assertEqual(result["agent_output"]["tool_name"], "query_weather_tool")
        self.assertEqual(
            result["agent_output"]["tool_input"],
            {"city": state["request"].city, "date_range": [state["request"].start_date, state["request"].end_date]},
        )

    @patch("app.agents.graph_nodes.get_settings", return_value=SimpleNamespace(info_gathering_use_llm=True))
    @patch(
        "app.agents.graph_nodes.create_llm",
        return_value=FakeLLM(
            json.dumps(
                {
                    "action": "submit_context",
                    "tool_name": None,
                    "reasoning_summary": "Looks ready.",
                    "ready_for_planning": True,
                },
                ensure_ascii=False,
            )
        ),
    )
    def test_info_gathering_llm_cannot_submit_before_required_sop(self, _llm, _settings):
        state = self.base_state()
        result = info_gathering_agent_node(state)
        self.assertEqual(result["agent_output"]["action"], "call_tool")
        self.assertEqual(result["agent_output"]["tool_name"], "search_attractions_tool")
        self.assertFalse(result["agent_output"]["ready_for_planning"])

    @patch("app.agents.graph_nodes.get_settings", return_value=SimpleNamespace(info_gathering_use_llm=True))
    @patch(
        "app.agents.graph_nodes.create_llm",
        return_value=FakeLLM(
            json.dumps(
                {
                    "action": "call_tool",
                    "tool_name": "search_local_events_tool",
                    "reasoning_summary": "Optional local events sound useful.",
                    "ready_for_planning": False,
                },
                ensure_ascii=False,
            )
        ),
    )
    def test_info_gathering_llm_cannot_use_local_events_to_skip_required_sop(self, _llm, _settings):
        state = self.base_state()
        result = info_gathering_agent_node(state)
        self.assertEqual(result["agent_output"]["action"], "call_tool")
        self.assertEqual(result["agent_output"]["tool_name"], "search_attractions_tool")

    @patch("app.agents.graph_nodes.get_settings", return_value=SimpleNamespace(info_gathering_use_llm=True))
    @patch("app.agents.graph_nodes.create_llm", return_value=FakeLLM("not json"))
    def test_info_gathering_llm_bad_json_falls_back_to_rules(self, _llm, _settings):
        state = self.base_state()
        state["sop_completed"]["attractions_done"] = True
        result = info_gathering_agent_node(state)
        self.assertEqual(result["agent_output"]["action"], "call_tool")
        self.assertEqual(result["agent_output"]["tool_name"], "query_weather_tool")

    @patch("app.agents.graph_nodes.create_llm", side_effect=AssertionError("LLM fallback should not be used"))
    @patch("app.agents.tools.attractions_tool.get_amap_service", return_value=EmptyAmapService())
    def test_search_attractions_no_result_does_not_fallback_to_llm(self, _amap, _llm):
        state = self.base_state()
        tool_result = search_attractions_node(state)
        result = merge_tool_result_node({**state, **tool_result})
        self.assertFalse(result["sop_completed"]["attractions_done"])
        self.assertEqual(json.loads(result["attractions_data"]), [])
        self.assertIn("warning", result["tool_call_history"][-1])

    @patch("app.agents.graph_nodes.create_llm", side_effect=AssertionError("LLM fallback should not be used"))
    @patch("app.agents.tools.weather_tool.get_amap_service", return_value=EmptyAmapService())
    def test_query_weather_no_result_does_not_fallback_to_llm(self, _amap, _llm):
        state = self.base_state()
        tool_result = query_weather_node(state)
        result = merge_tool_result_node({**state, **tool_result})
        self.assertFalse(result["sop_completed"]["weather_done"])
        self.assertEqual(json.loads(result["weather_data"]), [])
        self.assertIn("warning", result["tool_call_history"][-1])

    @patch("app.agents.graph_nodes.create_llm", side_effect=AssertionError("LLM fallback should not be used"))
    @patch("app.agents.tools.hotels_tool.get_amap_service", return_value=EmptyAmapService())
    def test_search_hotels_no_result_does_not_fallback_to_llm(self, _amap, _llm):
        state = self.base_state()
        tool_result = search_hotels_node(state)
        result = merge_tool_result_node({**state, **tool_result})
        self.assertFalse(result["sop_completed"]["hotels_done"])
        self.assertEqual(json.loads(result["hotel_data"]), [])
        self.assertIn("warning", result["tool_call_history"][-1])

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
