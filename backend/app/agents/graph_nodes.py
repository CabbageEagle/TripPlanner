"""LangGraph 节点函数定义"""

from typing import Dict, Any, Literal
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from .graph_state import TripPlannerState
from ..config import get_settings
from ..services.scheduler_service import ScheduleConfig, schedule_day_plan
import json


def create_llm():
    """创建LLM实例"""
    settings = get_settings()
    return ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        temperature=0.7
    )


def search_attractions_node(state: TripPlannerState) -> Dict[str, Any]:
    """景点搜索节点"""
    print("[GRAPH] 正在搜索景点...")
    
    request = state["request"]
    llm = create_llm()
    
    # 构建系统提示词
    system_prompt = """你是景点搜索专家。请根据用户的城市和偏好，生成详细的景点列表。

返回格式（JSON）:
```json
[
  {
    "name": "景点名称",
    "address": "详细地址",
    "location": {"longitude": 116.397128, "latitude": 39.916527},
    "visit_duration": 120,
    "description": "景点详细描述",
    "category": "景点类别",
    "ticket_price": 60
  }
]
```

注意：
1. 提供真实的景点信息
2. 经纬度坐标要准确
3. 根据偏好筛选合适的景点
4. 每天需要2-3个景点
"""
    
    # 构建用户查询
    keywords = ', '.join(request.preferences) if request.preferences else "热门景点"
    user_query = f"""请为{request.city}推荐适合{request.travel_days}天旅行的景点。
    
用户偏好: {keywords}
旅行天数: {request.travel_days}天

请返回至少{request.travel_days * 2}个景点的JSON列表。"""
    
    # 调用LLM
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_query)
    ]
    
    response = llm.invoke(messages)
    attractions_data = response.content
    
    print(f"[GRAPH] 景点搜索完成: {len(attractions_data)} 字符")
    
    return {
        "attractions_data": attractions_data,
        "current_step": "attractions_searched"
    }


def query_weather_node(state: TripPlannerState) -> Dict[str, Any]:
    """天气查询节点"""
    print("🌤️  正在查询天气...")
    
    request = state["request"]
    llm = create_llm()
    
    # 构建系统提示词
    system_prompt = """你是天气查询专家。请根据城市和日期，生成天气预报信息。

返回格式（JSON）:
```json
[
  {
    "date": "YYYY-MM-DD",
    "day_weather": "晴",
    "night_weather": "多云",
    "day_temp": 25,
    "night_temp": 15,
    "wind_direction": "南风",
    "wind_power": "1-3级"
  }
]
```

注意：
1. 为每一天提供天气信息
2. 温度为纯数字（不带单位）
3. 天气描述要简洁
"""
    
    # 构建用户查询
    user_query = f"""请为{request.city}提供{request.start_date}到{request.end_date}（共{request.travel_days}天）的天气预报。"""
    
    # 调用LLM
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_query)
    ]
    
    response = llm.invoke(messages)
    weather_data = response.content
    
    print(f"[GRAPH] 天气查询完成: {len(weather_data)} 字符")
    
    return {
        "weather_data": weather_data,
        "current_step": "weather_queried"
    }


def search_hotels_node(state: TripPlannerState) -> Dict[str, Any]:
    """酒店搜索节点"""
    print("[GRAPH] 正在搜索酒店...")
    
    request = state["request"]
    llm = create_llm()
    
    # 构建系统提示词
    system_prompt = """你是酒店推荐专家。请根据城市和住宿类型，推荐合适的酒店。

返回格式（JSON）:
```json
[
  {
    "name": "酒店名称",
    "address": "酒店地址",
    "location": {"longitude": 116.397128, "latitude": 39.916527},
    "price_range": "300-500元",
    "rating": "4.5",
    "distance": "距离市中心2公里",
    "type": "经济型酒店",
    "estimated_cost": 400
  }
]
```

注意：
1. 提供真实的酒店信息
2. 价格要合理
3. 根据住宿偏好筛选
"""
    
    # 构建用户查询
    user_query = f"""请为{request.city}推荐{request.accommodation}类型的酒店，需要住{request.travel_days}晚。
    
推荐至少3个不同价位的酒店。"""
    
    # 调用LLM
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_query)
    ]
    
    response = llm.invoke(messages)
    hotel_data = response.content
    
    print(f"[GRAPH] 酒店搜索完成: {len(hotel_data)} 字符")
    
    return {
        "hotel_data": hotel_data,
        "current_step": "hotels_searched"
    }


def plan_trip_node(state: TripPlannerState) -> Dict[str, Any]:
    """行程规划节点"""
    print("[GRAPH] 正在生成行程计划...")
    
    request = state["request"]
    attractions_data = state.get("attractions_data", "")
    weather_data = state.get("weather_data", "")
    hotel_data = state.get("hotel_data", "")
    inferred_preferences = state.get("inferred_preferences", "")
    
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
"""

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
            "current_step": "schedule_skipped"
        }

    schedule_retry_count = state.get("schedule_retry_count", 0)

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
            "current_step": "schedule_skipped"
        }

    warnings: list[str] = []
    schedule_failed = False
    scheduled_days: list[dict[str, Any]] = []
    for idx, day in enumerate(days):
        if not isinstance(day, dict):
            scheduled_days.append(day)
            continue
        try:
            scheduled_day, day_warnings = schedule_day_plan(day, cfg)
            scheduled_days.append(scheduled_day)
            warnings.extend([f"第{idx + 1}天: {warning}" for warning in day_warnings])
        except Exception as exc:
            schedule_failed = True
            warnings.append(f"第{idx + 1}天排程失败: {exc}")
            scheduled_days.append(day)

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


def fix_plan_node(state: TripPlannerState) -> Dict[str, Any]:
    """修复节点：根据校验问题精准修复计划"""
    print("[GRAPH] 正在修复行程计划...")
    
    violations = state.get("violations", [])
    final_plan = state.get("final_plan", {})
    request = state["request"]
    llm = create_llm()
    
    # 只提取可修复的 critical 或 high 级别问题
    fixable_issues = [
        v for v in violations 
        if v.get("severity") in ["critical", "high"] and v.get("fixable", True)
    ]
    
    # 如果没有可修复问题，直接返回原计划
    if not fixable_issues:
        print("[GRAPH] 没有可修复的问题，保持原计划")
        return {
            "final_plan_raw": json.dumps(final_plan, ensure_ascii=False),
            "current_step": "plan_fixed"
        }
    
    # 构建精准的修复指令，包含详细错误
    issues_text = []
    for i, v in enumerate(fixable_issues):
        issue_line = f"{i+1}. {v['message']}"
        
        # 添加期望值和实际值
        if 'expected' in v:
            issue_line += f" (期望: {v.get('expected')}, 实际: {v.get('actual')})"
        
        # 添加详细错误列表
        if 'details' in v and v['details']:
            issue_line += "\n   详细问题:"
            for detail in v['details']:
                issue_line += f"\n   - {detail}"
        
        issues_text.append(issue_line)
    
    issues_text = "\n".join(issues_text)
    
    # 构建修复提示词 - 更精简和精准
    system_prompt = f"""你是行程修复专家。请针对以下 {len(fixable_issues)} 个具体问题进行精准修复：

**需要修复的问题：**
{issues_text}

**修复规则：**
1. 只修复列出的问题（特别注意补充缺失的字段）
2. 保持其他部分完全不变
3. 景点必须包含：name, description, location(含longitude/latitude), visit_duration, address
4. 如果是天数问题，增加或减少相应天数的行程
5. 确保修复后的计划完整有效
6. 返回完整 JSON（不要省略任何部分）

**原始需求回顾：**
- 城市: {request.city}
- 天数: {request.travel_days}天
- 日期: {request.start_date} 至 {request.end_date}
- 偏好: {', '.join(request.preferences) if request.preferences else '无'}

返回完整的修复后 JSON:
```json
{{
  "city": "...",
  "start_date": "...",
  "end_date": "...",
  "days": [...],
  "weather_info": [...],
  "overall_suggestions": "...",
  "budget": {{...}}
}}
```
"""
    
    user_query = f"当前计划:\n{json.dumps(final_plan, ensure_ascii=False, indent=2)}"
    
    # 调用 LLM 修复
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_query)
    ]
    
    response = llm.invoke(messages)
    fixed_plan_raw = response.content
    
    print(f"[GRAPH] 修复完成: {len(fixed_plan_raw)} 字符")
    
    return {
        "final_plan_raw": fixed_plan_raw,
        "verify_count": state.get("verify_count", 0) + 1,  # 修复后增加计数
        "current_step": "plan_fixed"
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
