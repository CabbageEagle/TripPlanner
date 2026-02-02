"""验证节点：时间冲突检测和预算限制检查"""

from typing import Dict, Any, List, Tuple
from datetime import datetime, timedelta
from .graph_state import TripPlannerState
from ..models.schemas import Conflict, BudgetUsage, TimelineItem


def check_time_conflicts_node(state: TripPlannerState) -> Dict[str, Any]:
    """检查时间冲突"""
    print("⏰ 正在检查时间冲突...")
    
    final_plan = state.get("final_plan")
    request = state["request"]
    
    if not final_plan:
        return {"time_conflicts": []}
    
    conflicts = []
    
    # 获取时间限制
    daily_start = request.daily_start_time or "09:00"
    daily_end = request.daily_end_time or "21:00"
    max_attractions = request.max_attractions_per_day or 4
    
    for day in final_plan.get("days", []):
        day_index = day.get("day_index", 0)
        day_date = day.get("date", "")
        
        # 检查景点数量
        attractions = day.get("attractions", [])
        if len(attractions) > max_attractions:
            conflicts.append({
                "conflict_type": "capacity",
                "severity": "warning",
                "description": f"第{day_index+1}天景点数量({len(attractions)})超过限制({max_attractions})",
                "affected_items": [a.get("name", "") for a in attractions],
                "day_index": day_index
            })
        
        # 生成时间线并检查冲突
        timeline = _generate_timeline(day, daily_start, daily_end)
        day_conflicts = _detect_timeline_conflicts(timeline, day_index, daily_end)
        conflicts.extend(day_conflicts)
    
    if conflicts:
        print(f"⚠️  发现 {len(conflicts)} 个时间相关问题")
    else:
        print("✓ 未发现时间冲突")
    
    return {
        "time_conflicts": conflicts,
        "current_step": "time_checked"
    }


def check_budget_limits_node(state: TripPlannerState) -> Dict[str, Any]:
    """检查预算限制"""
    print("💰 正在检查预算限制...")
    
    final_plan = state.get("final_plan")
    request = state["request"]
    
    if not final_plan:
        return {"budget_usage": None}
    
    max_budget = request.max_budget
    budget_per_day = request.budget_per_day
    
    # 计算实际费用
    total_used = 0
    breakdown = {
        "attractions": 0,
        "meals": 0,
        "hotels": 0,
        "transportation": 0
    }
    
    conflicts = []
    
    for day in final_plan.get("days", []):
        day_index = day.get("day_index", 0)
        day_cost = 0
        
        # 景点费用
        for attraction in day.get("attractions", []):
            cost = attraction.get("ticket_price", 0)
            breakdown["attractions"] += cost
            day_cost += cost
        
        # 餐饮费用
        for meal in day.get("meals", []):
            cost = meal.get("estimated_cost", 0)
            breakdown["meals"] += cost
            day_cost += cost
        
        # 酒店费用
        hotel = day.get("hotel")
        if hotel:
            cost = hotel.get("estimated_cost", 0)
            breakdown["hotels"] += cost
            day_cost += cost
        
        # 检查每日预算
        if budget_per_day and day_cost > budget_per_day:
            conflicts.append({
                "conflict_type": "budget",
                "severity": "warning",
                "description": f"第{day_index+1}天费用({day_cost}元)超过每日预算({budget_per_day}元)",
                "affected_items": [f"第{day_index+1}天"],
                "day_index": day_index
            })
    
    # 计算总费用
    total_used = sum(breakdown.values())
    
    # 交通费用（估算）
    days_count = len(final_plan.get("days", []))
    estimated_transport = days_count * 50  # 每天估算50元交通费
    breakdown["transportation"] = estimated_transport
    total_used += estimated_transport
    
    # 检查总预算
    over_budget = False
    over_amount = 0
    remaining = 0
    
    if max_budget:
        over_budget = total_used > max_budget
        over_amount = max(0, total_used - max_budget)
        remaining = max(0, max_budget - total_used)
        
        if over_budget:
            conflicts.append({
                "conflict_type": "budget",
                "severity": "critical",
                "description": f"总费用({total_used}元)超过预算限制({max_budget}元)",
                "affected_items": ["总预算"],
                "day_index": None
            })
    else:
        remaining = 0
    
    budget_usage = {
        "total_budget": max_budget or total_used,
        "used_budget": total_used,
        "remaining_budget": remaining,
        "breakdown": breakdown,
        "over_budget": over_budget,
        "over_budget_amount": over_amount
    }
    
    if conflicts:
        print(f"⚠️  发现 {len(conflicts)} 个预算问题")
        # 将预算冲突合并到总冲突列表
        existing_conflicts = state.get("time_conflicts", [])
        all_conflicts = existing_conflicts + conflicts if existing_conflicts else conflicts
    else:
        print(f"✓ 预算检查通过 (使用: {total_used}元)")
        all_conflicts = state.get("time_conflicts", [])
    
    return {
        "budget_usage": budget_usage,
        "time_conflicts": all_conflicts,  # 合并所有冲突
        "current_step": "budget_checked"
    }


def _generate_timeline(day: Dict[str, Any], start_time: str, end_time: str) -> List[TimelineItem]:
    """生成一天的时间线"""
    timeline = []
    current_time = datetime.strptime(start_time, "%H:%M")
    
    attractions = day.get("attractions", [])
    meals = day.get("meals", [])
    
    # 简化处理：早餐 -> 景点 -> 午餐 -> 景点 -> 晚餐
    
    # 早餐
    breakfast = next((m for m in meals if m.get("type") == "breakfast"), None)
    if breakfast:
        timeline.append({
            "start_time": current_time.strftime("%H:%M"),
            "end_time": (current_time + timedelta(minutes=30)).strftime("%H:%M"),
            "activity_type": "meal",
            "activity_name": breakfast.get("name", "早餐"),
            "duration": 30,
            "cost": breakfast.get("estimated_cost", 0)
        })
        current_time += timedelta(minutes=30)
    
    # 上午景点
    for i, attraction in enumerate(attractions[:2]):
        # 移动时间
        if i > 0:
            current_time += timedelta(minutes=20)  # 移动时间
        
        duration = attraction.get("visit_duration", 120)
        timeline.append({
            "start_time": current_time.strftime("%H:%M"),
            "end_time": (current_time + timedelta(minutes=duration)).strftime("%H:%M"),
            "activity_type": "attraction",
            "activity_name": attraction.get("name", ""),
            "duration": duration,
            "cost": attraction.get("ticket_price", 0)
        })
        current_time += timedelta(minutes=duration)
    
    # 午餐
    lunch = next((m for m in meals if m.get("type") == "lunch"), None)
    if lunch:
        timeline.append({
            "start_time": current_time.strftime("%H:%M"),
            "end_time": (current_time + timedelta(minutes=60)).strftime("%H:%M"),
            "activity_type": "meal",
            "activity_name": lunch.get("name", "午餐"),
            "duration": 60,
            "cost": lunch.get("estimated_cost", 0)
        })
        current_time += timedelta(minutes=60)
    
    # 下午景点
    for i, attraction in enumerate(attractions[2:]):
        if i > 0:
            current_time += timedelta(minutes=20)
        
        duration = attraction.get("visit_duration", 120)
        timeline.append({
            "start_time": current_time.strftime("%H:%M"),
            "end_time": (current_time + timedelta(minutes=duration)).strftime("%H:%M"),
            "activity_type": "attraction",
            "activity_name": attraction.get("name", ""),
            "duration": duration,
            "cost": attraction.get("ticket_price", 0)
        })
        current_time += timedelta(minutes=duration)
    
    # 晚餐
    dinner = next((m for m in meals if m.get("type") == "dinner"), None)
    if dinner:
        timeline.append({
            "start_time": current_time.strftime("%H:%M"),
            "end_time": (current_time + timedelta(minutes=60)).strftime("%H:%M"),
            "activity_type": "meal",
            "activity_name": dinner.get("name", "晚餐"),
            "duration": 60,
            "cost": dinner.get("estimated_cost", 0)
        })
        current_time += timedelta(minutes=60)
    
    return timeline


def _detect_timeline_conflicts(
    timeline: List[TimelineItem], 
    day_index: int,
    daily_end_time: str
) -> List[Dict[str, Any]]:
    """检测时间线中的冲突"""
    conflicts = []
    
    if not timeline:
        return conflicts
    
    # 检查是否超过每日结束时间
    last_item = timeline[-1]
    end_time = datetime.strptime(last_item["end_time"], "%H:%M")
    daily_end = datetime.strptime(daily_end_time, "%H:%M")
    
    if end_time > daily_end:
        conflicts.append({
            "conflict_type": "time",
            "severity": "warning",
            "description": f"第{day_index+1}天行程结束时间({last_item['end_time']})超过限制({daily_end_time})",
            "affected_items": [last_item["activity_name"]],
            "day_index": day_index
        })
    
    # 检查时间重叠
    for i in range(len(timeline) - 1):
        current_end = datetime.strptime(timeline[i]["end_time"], "%H:%M")
        next_start = datetime.strptime(timeline[i+1]["start_time"], "%H:%M")
        
        if current_end > next_start:
            conflicts.append({
                "conflict_type": "time",
                "severity": "critical",
                "description": f"活动时间重叠: {timeline[i]['activity_name']} 与 {timeline[i+1]['activity_name']}",
                "affected_items": [timeline[i]["activity_name"], timeline[i+1]["activity_name"]],
                "day_index": day_index
            })
    
    return conflicts
