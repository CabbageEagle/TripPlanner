"""使用 LangGraph 框架的旅行规划系统"""

import json
from typing import Dict, Any
from langgraph.graph import StateGraph, END
from .graph_state import TripPlannerState
from .graph_nodes import (
    init_info_gathering_node,
    sop_bootstrap_node,
    info_gathering_agent_node,
    search_attractions_node,
    query_weather_node,
    search_hotels_node,
    search_local_events_node,
    estimate_transit_time_node,
    merge_tool_result_node,
    router_warning_node,
    forced_exit_with_best_effort_node,
    plan_trip_node,
    parse_plan_node,
    schedule_plan_node,
    verify_plan_node,
    fix_plan_node,
    error_handler_node,
    build_agent_diagnostics,
    normalize_trip_plan_payload,
    info_gathering_router,
    should_retry_parse,
    should_fix_or_end
)
from ..models.schemas import TripRequest, TripPlan
from ..config import get_settings


class LangGraphTripPlanner:
    """基于 LangGraph 的旅行规划系统"""
    
    def __init__(self):
        """初始化 LangGraph 工作流"""
        print("[LANGGRAPH] 开始初始化旅行规划系统...")
        
        # 创建状态图
        workflow = StateGraph(TripPlannerState)
        
        # 添加节点
        workflow.add_node("init_info_gathering", init_info_gathering_node)
        workflow.add_node("sop_bootstrap", sop_bootstrap_node)
        workflow.add_node("info_gathering_agent", info_gathering_agent_node)
        workflow.add_node("search_attractions_tool", search_attractions_node)
        workflow.add_node("query_weather_tool", query_weather_node)
        workflow.add_node("search_hotels_tool", search_hotels_node)
        workflow.add_node("search_local_events_tool", search_local_events_node)
        workflow.add_node("estimate_transit_time_tool", estimate_transit_time_node)
        workflow.add_node("merge_tool_result", merge_tool_result_node)
        workflow.add_node("router_warning", router_warning_node)
        workflow.add_node("forced_exit_with_best_effort", forced_exit_with_best_effort_node)
        workflow.add_node("plan_trip", plan_trip_node)
        workflow.add_node("parse_plan", parse_plan_node)
        workflow.add_node("schedule_plan", schedule_plan_node)
        workflow.add_node("verify_plan", verify_plan_node)
        workflow.add_node("fix_plan", fix_plan_node)
        workflow.add_node("error_handler", error_handler_node)

        # 设置入口点
        workflow.set_entry_point("init_info_gathering")

        # 信息搜集子图
        workflow.add_edge("init_info_gathering", "sop_bootstrap")
        workflow.add_edge("sop_bootstrap", "info_gathering_agent")
        workflow.add_conditional_edges(
            "info_gathering_agent",
            info_gathering_router,
            {
                "search_attractions_tool": "search_attractions_tool",
                "query_weather_tool": "query_weather_tool",
                "search_hotels_tool": "search_hotels_tool",
                "search_local_events_tool": "search_local_events_tool",
                "estimate_transit_time_tool": "estimate_transit_time_tool",
                "router_warning": "router_warning",
                "forced_exit_with_best_effort": "forced_exit_with_best_effort",
                "plan_trip": "plan_trip",
                "info_gathering_agent": "info_gathering_agent",
            }
        )
        workflow.add_edge("search_attractions_tool", "merge_tool_result")
        workflow.add_edge("query_weather_tool", "merge_tool_result")
        workflow.add_edge("search_hotels_tool", "merge_tool_result")
        workflow.add_edge("search_local_events_tool", "merge_tool_result")
        workflow.add_edge("estimate_transit_time_tool", "merge_tool_result")
        workflow.add_edge("merge_tool_result", "info_gathering_agent")
        workflow.add_edge("router_warning", "info_gathering_agent")
        workflow.add_edge("forced_exit_with_best_effort", "plan_trip")
        
        # 验证回环阶段
        workflow.add_edge("plan_trip", "parse_plan")
        
        # 条件边：解析成功进入验证，失败则重试或进入错误处理
        workflow.add_conditional_edges(
            "parse_plan",
            should_retry_parse,
            {
                "schedule_plan": "schedule_plan",
                "parse_plan": "parse_plan",
                "error_handler": "error_handler"
            }
        )

        workflow.add_edge("schedule_plan", "verify_plan")
        
        # 条件边：验证失败则修复，通过则结束
        workflow.add_conditional_edges(
            "verify_plan",
            should_fix_or_end,
            {
                "fix_plan": "fix_plan",
                "END": END
            }
        )
        
        # 修复后直接重新排程和复验，避免整份计划重新解析回环
        workflow.add_edge("fix_plan", "schedule_plan")
        
        # 错误处理直接结束
        workflow.add_edge("error_handler", END)
        
        # 编译图
        self.app = workflow.compile()
        
        print("[LANGGRAPH] 旅行规划系统初始化成功")
        print("   流程: 数据收集 -> 规划 -> 解析 -> 校验 -> [修复回环] -> 结束")
    
    def plan_trip(self, request: TripRequest, inferred_preferences: str | None = None) -> TripPlan:
        """使用 LangGraph 生成旅行计划。"""
        trip_plan, _diagnostics = self.plan_trip_with_diagnostics(request, inferred_preferences)
        return trip_plan

    def plan_trip_with_diagnostics(
        self,
        request: TripRequest,
        inferred_preferences: str | None = None,
    ) -> tuple[TripPlan, dict[str, Any]]:
        """
        使用 LangGraph 生成旅行计划，并返回 Agent 诊断快照。
        
        Args:
            request: 旅行请求
            
        Returns:
            旅行计划和诊断信息
        """
        try:
            print(f"\n{'='*60}")
            print("[LANGGRAPH] 开始执行工作流...")
            print(f"目的地: {request.city}")
            print(f"日期: {request.start_date} 至 {request.end_date}")
            print(f"天数: {request.travel_days}天")
            print(f"偏好: {', '.join(request.preferences) if request.preferences else '无'}")
            print(f"{'='*60}\n")
            
            # 初始化状态
            initial_state: TripPlannerState = {
                "request": request,
                "memory_summary": "",
                "base_constraints": {},
                "attractions_data": None,
                "weather_data": None,
                "hotel_data": None,
                "inferred_preferences": inferred_preferences,
                "sop_required": {
                    "weather_required": True,
                    "attractions_required": True,
                    "hotels_required": False,
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
                "error": None
            }
            
            # 运行工作流
            final_state = self.app.invoke(initial_state)
            loop_count = final_state.get("loop_count", 0)
            # 获取最终计划（已经是结构化数据）
            final_plan_dict = final_state.get("final_plan")
            
            # 如果 final_plan 是 None，尝试从 final_plan_raw 解析
            if final_plan_dict is None:
                final_plan_str = final_state.get("final_plan_raw", "")
                trip_plan = self._parse_response(final_plan_str, request)
            else:
                # 直接转换为 TripPlan 对象
                try:
                    source_weather = (final_state.get("gathered_context") or {}).get("weather")
                    final_plan_dict = normalize_trip_plan_payload(final_plan_dict, request, source_weather)
                    trip_plan = TripPlan(**final_plan_dict)
                except Exception as e:
                    print(f"[LANGGRAPH] 转换为 TripPlan 失败: {str(e)}")
                    raise ValueError(f"结构化计划校验失败: {str(e)}") from e
            
            # 打印验证统计
            verify_count = final_state.get("verify_count", 0)
            violations = final_state.get("violations")

            print(f"\n{'='*60}")
            print("[LANGGRAPH] 旅行计划生成完成")
            print(f"   验证次数: {verify_count}")
            print(f"[LANGGRAPH] info_gathering loop_count: {loop_count}")
                  
            if violations:
                print(f"   [WARN] 存在 {len(violations)} 个未解决的问题")
            else:
                print("   [OK] 所有验证通过")
            print(f"{'='*60}\n")
            
            return trip_plan, build_agent_diagnostics(final_state)
            
        except Exception as e:
            print(f"[LANGGRAPH] 生成旅行计划失败: {str(e)}")
            import traceback
            traceback.print_exc()
            raise RuntimeError(f"生成旅行计划失败: {str(e)}") from e
    
    def _parse_response(self, response: str, request: TripRequest) -> TripPlan:
        """
        解析响应
        
        Args:
            response: 响应文本
            request: 原始请求
            
        Returns:
            旅行计划
        """
        try:
            # 尝试从响应中提取JSON
            if "```json" in response:
                json_start = response.find("```json") + 7
                json_end = response.find("```", json_start)
                json_str = response[json_start:json_end].strip()
            elif "```" in response:
                json_start = response.find("```") + 3
                json_end = response.find("```", json_start)
                json_str = response[json_start:json_end].strip()
            elif "{" in response and "}" in response:
                # 直接查找JSON对象
                json_start = response.find("{")
                json_end = response.rfind("}") + 1
                json_str = response[json_start:json_end]
            else:
                raise ValueError("响应中未找到JSON数据")
            
            # 解析JSON
            data = normalize_trip_plan_payload(json.loads(json_str), request)
            
            # 转换为TripPlan对象
            trip_plan = TripPlan(**data)
            
            return trip_plan
            
        except Exception as e:
            print(f"[LANGGRAPH] 解析响应失败: {str(e)}")
            raise ValueError(f"解析模型响应失败: {str(e)}") from e
    
    def _create_fallback_plan(self, request: TripRequest) -> TripPlan:
        """创建备用计划(当流程失败时)"""
        from datetime import datetime, timedelta
        from ..models.schemas import DayPlan, Attraction, Meal, Location
        
        # 解析日期
        start_date = datetime.strptime(request.start_date, "%Y-%m-%d")
        
        # 创建每日行程
        days = []
        for i in range(request.travel_days):
            current_date = start_date + timedelta(days=i)
            
            day_plan = DayPlan(
                date=current_date.strftime("%Y-%m-%d"),
                day_index=i,
                description=f"第{i+1}天行程",
                transportation=request.transportation,
                accommodation=request.accommodation,
                attractions=[
                    Attraction(
                        name=f"{request.city}景点{j+1}",
                        address=f"{request.city}市",
                        location=Location(
                            longitude=116.4 + i*0.01 + j*0.005,
                            latitude=39.9 + i*0.01 + j*0.005
                        ),
                        visit_duration=120,
                        description=f"这是{request.city}的著名景点",
                        category="景点"
                    )
                    for j in range(2)
                ],
                meals=[
                    Meal(type="breakfast", name=f"第{i+1}天早餐", description="当地特色早餐"),
                    Meal(type="lunch", name=f"第{i+1}天午餐", description="午餐推荐"),
                    Meal(type="dinner", name=f"第{i+1}天晚餐", description="晚餐推荐")
                ]
            )
            days.append(day_plan)
        
        return TripPlan(
            city=request.city,
            start_date=request.start_date,
            end_date=request.end_date,
            days=days,
            weather_info=[],
            overall_suggestions=f"这是为您规划的{request.city}{request.travel_days}日游行程，建议提前查看各景点的开放时间。"
        )


# 全局 LangGraph 规划器实例
_langgraph_planner = None


def get_trip_planner_agent() -> LangGraphTripPlanner:
    """获取 LangGraph 旅行规划系统实例(单例模式)"""
    global _langgraph_planner
    
    if _langgraph_planner is None:
        _langgraph_planner = LangGraphTripPlanner()
    
    return _langgraph_planner
