"""使用 LangGraph 框架的旅行规划系统"""

import json
from typing import Dict, Any
from langgraph.graph import StateGraph, END
from .graph_state import TripPlannerState
from .graph_nodes import (
    search_attractions_node,
    query_weather_node,
    search_hotels_node,
    plan_trip_node,
    parse_plan_node,
    verify_plan_node,
    fix_plan_node,
    error_handler_node,
    should_retry_parse,
    should_fix_or_end
)
from ..models.schemas import TripRequest, TripPlan
from ..config import get_settings


class LangGraphTripPlanner:
    """基于 LangGraph 的旅行规划系统"""
    
    def __init__(self):
        """初始化 LangGraph 工作流"""
        print("🔄 开始初始化 LangGraph 旅行规划系统...")
        
        # 创建状态图
        workflow = StateGraph(TripPlannerState)
        
        # 添加节点
        workflow.add_node("search_attractions", search_attractions_node)
        workflow.add_node("query_weather", query_weather_node)
        workflow.add_node("search_hotels", search_hotels_node)
        workflow.add_node("plan_trip", plan_trip_node)
        workflow.add_node("parse_plan", parse_plan_node)
        workflow.add_node("verify_plan", verify_plan_node)
        workflow.add_node("fix_plan", fix_plan_node)
        workflow.add_node("error_handler", error_handler_node)
        
        # 设置入口点
        workflow.set_entry_point("search_attractions")
        
        # 添加边（定义工作流）
        workflow.add_edge("search_attractions", "query_weather")
        workflow.add_edge("query_weather", "search_hotels")
        workflow.add_edge("search_hotels", "plan_trip")
        
        # 验证回环阶段
        workflow.add_edge("plan_trip", "parse_plan")
        
        # 条件边：解析成功进入验证，失败则重试或进入错误处理
        workflow.add_conditional_edges(
            "parse_plan",
            should_retry_parse,
            {
                "verify_plan": "verify_plan",
                "parse_plan": "parse_plan",
                "error_handler": "error_handler"
            }
        )
        
        # 条件边：验证失败则修复，通过则结束
        workflow.add_conditional_edges(
            "verify_plan",
            should_fix_or_end,
            {
                "fix_plan": "fix_plan",
                "END": END
            }
        )
        
        # 修复后重新解析
        workflow.add_edge("fix_plan", "parse_plan")
        
        # 错误处理直接结束
        workflow.add_edge("error_handler", END)
        
        # 编译图
        self.app = workflow.compile()
        
        print("✅ LangGraph 旅行规划系统初始化成功")
        print("   流程: 数据收集 -> 规划 -> 解析 -> 校验 -> [修复回环] -> 结束")
    
    def plan_trip(self, request: TripRequest) -> TripPlan:
        """
        使用 LangGraph 生成旅行计划
        
        Args:
            request: 旅行请求
            
        Returns:
            旅行计划
        """
        try:
            print(f"\n{'='*60}")
            print(f"🚀 开始 LangGraph 工作流...")
            print(f"目的地: {request.city}")
            print(f"日期: {request.start_date} 至 {request.end_date}")
            print(f"天数: {request.travel_days}天")
            print(f"偏好: {', '.join(request.preferences) if request.preferences else '无'}")
            print(f"{'='*60}\n")
            
            # 初始化状态
            initial_state: TripPlannerState = {
                "request": request,
                "attractions_data": None,
                "weather_data": None,
                "hotel_data": None,
                "final_plan_raw": None,
                "final_plan": None,
                "violations": None,
                "verify_count": 0,
                "parse_retry_count": 0,
                "current_step": "initialized",
                "error": None
            }
            
            # 运行工作流
            final_state = self.app.invoke(initial_state)
            
            # 获取最终计划（已经是结构化数据）
            final_plan_dict = final_state.get("final_plan")
            
            # 如果 final_plan 是 None，尝试从 final_plan_raw 解析
            if final_plan_dict is None:
                final_plan_str = final_state.get("final_plan_raw", "")
                trip_plan = self._parse_response(final_plan_str, request)
            else:
                # 直接转换为 TripPlan 对象
                try:
                    trip_plan = TripPlan(**final_plan_dict)
                except Exception as e:
                    print(f"⚠️  转换为 TripPlan 失败: {str(e)}, 使用备用方案")
                    trip_plan = self._create_fallback_plan(request)
            
            # 打印验证统计
            verify_count = final_state.get("verify_count", 0)
            violations = final_state.get("violations")
            print(f"\n{'='*60}")
            print(f"✅ 旅行计划生成完成!")
            print(f"   验证次数: {verify_count}")
            if violations:
                print(f"   ⚠️  存在 {len(violations)} 个未解决的问题")
            else:
                print(f"   ✓ 所有验证通过")
            print(f"{'='*60}\n")
            
            return trip_plan
            
        except Exception as e:
            print(f"❌ 生成旅行计划失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return self._create_fallback_plan(request)
    
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
            data = json.loads(json_str)
            
            # 转换为TripPlan对象
            trip_plan = TripPlan(**data)
            
            return trip_plan
            
        except Exception as e:
            print(f"⚠️  解析响应失败: {str(e)}")
            print(f"   将使用备用方案生成计划")
            return self._create_fallback_plan(request)
    
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
