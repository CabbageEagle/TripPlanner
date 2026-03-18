from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from ..config import get_settings
from .amap_service import get_amap_service


@dataclass
class ScheduleConfig:
    daily_start_time: str = "09:00"
    daily_end_time: str = "21:00"
    min_rest_time: int = 15
    default_travel_minutes: int = 20
    route_type: str = "walking"
    city: str = ""


def schedule_trip_plan(plan: dict[str, Any], cfg: ScheduleConfig) -> tuple[dict[str, Any], list[str]]:
    """对完整 TripPlan 进行排程，返回更新后的计划和告警列表。"""
    if not isinstance(plan, dict):
        return plan, ["排程跳过: plan 非字典结构"]

    days = plan.get("days")
    if not isinstance(days, list):
        return plan, ["排程跳过: days 字段不是列表"]

    warnings: list[str] = []
    scheduled_days: list[Any] = []

    for idx, day in enumerate(days):
        if not isinstance(day, dict):
            warnings.append(f"第{idx + 1}天排程跳过: day 非字典结构")
            scheduled_days.append(day)
            continue

        try:
            scheduled_day, day_warnings = schedule_day_plan(day, cfg)
            scheduled_days.append(scheduled_day)
            warnings.extend([f"第{idx + 1}天: {warning}" for warning in day_warnings])
        except Exception as exc:
            warnings.append(f"第{idx + 1}天排程失败: {exc}")
            scheduled_days.append(day)

    plan["days"] = scheduled_days

    if warnings:
        existing_warnings = plan.get("warnings")
        if not isinstance(existing_warnings, list):
            existing_warnings = []
        existing_warnings.extend([f"排程: {item}" for item in warnings])
        plan["warnings"] = _dedupe_text_list(existing_warnings)

    return plan, warnings


def schedule_day_plan(day: dict[str, Any], cfg: ScheduleConfig) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []

    day_start = _to_minutes(cfg.daily_start_time, fallback=9 * 60)
    day_end = _to_minutes(cfg.daily_end_time, fallback=21 * 60)
    current = day_start

    timeline: list[dict[str, Any]] = []
    attractions = day.get("attractions") or []
    meals = day.get("meals") or []
    hotel = day.get("hotel") or {}

    lunch_meal = _pick_meal(meals, ["lunch", "午餐"])
    dinner_meal = _pick_meal(meals, ["dinner", "晚餐"])
    placed_lunch = False
    placed_dinner = False

    previous_stop_name = hotel.get("name") or day.get("accommodation") or "酒店"
    previous_stop_address = hotel.get("address") or ""

    for attraction in attractions:
        attraction_name = str(attraction.get("name") or "景点")
        attraction_address = str(attraction.get("address") or "")

        opening_hours = attraction.get("opening_hours")
        if not opening_hours:
            attraction["opening_hours"] = "未知"
        open_window = _parse_opening_window(str(opening_hours or ""))

        # 到达景点前先尝试插入午餐，避免被景点挤压到营业时间外。
        if (not placed_lunch) and lunch_meal and current >= _to_minutes("11:30", fallback=690):
            current = _insert_meal(
                timeline=timeline,
                meal=lunch_meal,
                current=current,
                day_end=day_end,
                default_duration=60,
                min_rest=cfg.min_rest_time,
            )
            placed_lunch = True

        travel_minutes = _estimate_travel_minutes(
            origin_name=previous_stop_name,
            origin_address=previous_stop_address,
            destination_name=attraction_name,
            destination_address=attraction_address,
            cfg=cfg,
        )
        if current + travel_minutes > day_end:
            warnings.append(f"时间不足，无法前往景点：{attraction_name}")
            break

        if travel_minutes > 0:
            _add_timeline_item(
                timeline=timeline,
                start=current,
                end=current + travel_minutes,
                activity_type="transport",
                activity_name=f"前往 {attraction_name}",
                location=None,
                cost=0,
            )
            current += travel_minutes

        if open_window is not None:
            open_start, open_end = open_window
            if current < open_start:
                current = open_start
            if current >= open_end:
                warnings.append(f"景点已接近闭馆，跳过：{attraction_name}")
                continue

        duration = _safe_int(attraction.get("visit_duration"), default=90, min_value=15)
        visit_start = current
        visit_end = visit_start + duration

        if open_window is not None and visit_end > open_window[1]:
            warnings.append(f"景点营业时间不足，跳过：{attraction_name}")
            continue
        if visit_end > day_end:
            warnings.append(f"超过当天结束时间，后续景点未排：{attraction_name}")
            break

        attraction["visit_start_time"] = _to_hhmm(visit_start)
        attraction["visit_end_time"] = _to_hhmm(visit_end)
        _add_timeline_item(
            timeline=timeline,
            start=visit_start,
            end=visit_end,
            activity_type="attraction",
            activity_name=attraction_name,
            location=attraction.get("location"),
            cost=_safe_int(attraction.get("ticket_price"), default=0),
        )
        current = visit_end + cfg.min_rest_time

        previous_stop_name = attraction_name
        previous_stop_address = attraction_address

        if (not placed_dinner) and dinner_meal and current >= _to_minutes("17:30", fallback=1050):
            current = _insert_meal(
                timeline=timeline,
                meal=dinner_meal,
                current=current,
                day_end=day_end,
                default_duration=70,
                min_rest=cfg.min_rest_time,
            )
            placed_dinner = True

    if (not placed_lunch) and lunch_meal and current < day_end:
        current = _insert_meal(
            timeline=timeline,
            meal=lunch_meal,
            current=max(current, _to_minutes("12:00", fallback=720)),
            day_end=day_end,
            default_duration=60,
            min_rest=cfg.min_rest_time,
        )
        placed_lunch = True

    if (not placed_dinner) and dinner_meal and current < day_end:
        _insert_meal(
            timeline=timeline,
            meal=dinner_meal,
            current=max(current, _to_minutes("18:00", fallback=1080)),
            day_end=day_end,
            default_duration=70,
            min_rest=cfg.min_rest_time,
        )

    day["timeline"] = timeline
    day["total_duration"] = sum(item.get("duration", 0) for item in timeline)
    day["total_cost"] = sum(item.get("cost", 0) or 0 for item in timeline)
    day["attractions"] = attractions
    return day, warnings


def _insert_meal(
    *,
    timeline: list[dict[str, Any]],
    meal: dict[str, Any],
    current: int,
    day_end: int,
    default_duration: int,
    min_rest: int,
) -> int:
    meal_duration = _safe_int(meal.get("duration"), default=default_duration, min_value=20)
    if current + meal_duration > day_end:
        return current

    _add_timeline_item(
        timeline=timeline,
        start=current,
        end=current + meal_duration,
        activity_type="meal",
        activity_name=str(meal.get("name") or meal.get("type") or "用餐"),
        location=meal.get("location"),
        cost=_safe_int(meal.get("estimated_cost"), default=0),
    )
    return current + meal_duration + min_rest


def _pick_meal(meals: list[dict[str, Any]], targets: list[str]) -> dict[str, Any] | None:
    normalized_targets = {item.lower() for item in targets}
    for meal in meals:
        meal_type = str(meal.get("type") or "").lower()
        if meal_type in normalized_targets:
            return meal
    return None


def _estimate_travel_minutes(
    *,
    origin_name: str,
    origin_address: str,
    destination_name: str,
    destination_address: str,
    cfg: ScheduleConfig,
) -> int:
    if not origin_address or not destination_address or origin_address == destination_address:
        return cfg.default_travel_minutes

    settings = get_settings()
    use_mcp_route = settings.schedule_use_mcp_route or bool(settings.amap_api_key)
    if not use_mcp_route:
        return cfg.default_travel_minutes

    if not settings.amap_api_key:
        return cfg.default_travel_minutes

    try:
        service = get_amap_service()
        route_info = service.plan_route(
            origin_address=origin_address,
            destination_address=destination_address,
            origin_city=cfg.city or None,
            destination_city=cfg.city or None,
            route_type=cfg.route_type,
        )
        duration = _safe_int(route_info.get("duration"), default=0)
        if duration > 0:
            return max(5, duration)
    except Exception as exc:
        print(f"[SCHED] route fallback ({origin_name}->{destination_name}): {exc}")

    return cfg.default_travel_minutes


def _parse_opening_window(text: str) -> tuple[int, int] | None:
    if not text:
        return None

    match = re.search(r"(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})", text)
    if not match:
        return None

    start = _to_minutes(match.group(1), fallback=0)
    end = _to_minutes(match.group(2), fallback=24 * 60)
    if end <= start:
        return None
    return start, end


def _add_timeline_item(
    *,
    timeline: list[dict[str, Any]],
    start: int,
    end: int,
    activity_type: str,
    activity_name: str,
    location: Any,
    cost: int,
) -> None:
    if end <= start:
        return
    timeline.append(
        {
            "start_time": _to_hhmm(start),
            "end_time": _to_hhmm(end),
            "activity_type": activity_type,
            "activity_name": activity_name,
            "duration": end - start,
            "location": location,
            "cost": cost,
        }
    )


def _to_minutes(text: str, *, fallback: int) -> int:
    try:
        hour_text, minute_text = text.strip().split(":")
        hour = int(hour_text)
        minute = int(minute_text)
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            return fallback
        return hour * 60 + minute
    except Exception:
        return fallback


def _to_hhmm(total_minutes: int) -> str:
    safe = max(0, min(23 * 60 + 59, total_minutes))
    hour = safe // 60
    minute = safe % 60
    return f"{hour:02d}:{minute:02d}"


def _safe_int(value: Any, *, default: int, min_value: int | None = None) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError):
        result = default
    if min_value is not None:
        result = max(min_value, result)
    return result


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