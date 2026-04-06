"""LangGraph 状态定义"""

from typing import TypedDict, List, Dict, Any, Optional
from ..models.schemas import TripRequest


class TripPlannerState(TypedDict):
    """旅行规划图的状态"""
    
    # 输入
    request: TripRequest
    
    # 中间结果
    attractions_data: Optional[str]
    weather_data: Optional[str]
    hotel_data: Optional[str]
    inferred_preferences: Optional[str]
    
    # 最终输出
    final_plan_raw: Optional[str]               #模型原始输出
    final_plan: Optional[Dict[str, Any]]       #parse解析后的结果

    #加入verify回环
    violations: Optional[list[Dict[str,Any]]]  # 修复拼写错误
    verify_count: int
    parse_retry_count: int
    schedule_applied: bool
    schedule_retry_count: int
    schedule_notes: list[str]
    days_to_reschedule: Optional[list[int]]
    
    # 控制流
    current_step: str
    error: Optional[str]
