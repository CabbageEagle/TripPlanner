"""高德地图 MCP 服务封装。"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from hello_agents.tools import MCPTool

from ..config import get_settings
from ..models.schemas import Location, POIInfo, WeatherInfo

_amap_mcp_tool: MCPTool | None = None
_amap_service: "AmapService | None" = None


def get_amap_mcp_tool() -> MCPTool:
    """获取高德地图 MCPTool 单例。"""
    global _amap_mcp_tool

    if _amap_mcp_tool is not None:
        return _amap_mcp_tool

    settings = get_settings()
    if not settings.amap_api_key:
        raise ValueError("AMAP_API_KEY 未配置，请在 .env 中设置后重试")

    _amap_mcp_tool = MCPTool(
        name="amap",
        description="高德地图服务，支持 POI、路线和天气相关工具",
        server_command=["uvx", "amap-mcp-server"],
        env={"AMAP_MAPS_API_KEY": settings.amap_api_key},
        auto_expand=True,
    )
    print(f"[AMAP] MCP 初始化完成，可用工具数: {len(_amap_mcp_tool._available_tools)}")
    return _amap_mcp_tool


class AmapService:
    """高德地图服务封装。"""

    def __init__(self) -> None:
        self.mcp_tool = get_amap_mcp_tool()

    def search_poi(self, keywords: str, city: str, citylimit: bool = True) -> list[POIInfo]:
        try:
            result = self.mcp_tool.run(
                {
                    "action": "call_tool",
                    "tool_name": "maps_text_search",
                    "arguments": {"keywords": keywords, "city": city, "citylimit": str(citylimit).lower()},
                }
            )
            payload = _normalize_mcp_result(result)
            pois = _extract_poi_list(payload)
            return pois
        except Exception as exc:
            print(f"[AMAP] POI 搜索失败: {exc}")
            return []

    def search_poi_with_raw(self, keywords: str, city: str, citylimit: bool = True) -> tuple[list[POIInfo], str | None]:
        try:
            result = self.mcp_tool.run(
                {
                    "action": "call_tool",
                    "tool_name": "maps_text_search",
                    "arguments": {"keywords": keywords, "city": city, "citylimit": str(citylimit).lower()},
                }
            )
            raw_text = str(result)
            payload = _normalize_mcp_result(result)
            raw_pois = _extract_raw_poi_items(payload)
            pois = _extract_poi_list(payload)
            if pois:
                return pois, None
            if payload:
                return [], (
                    f"AMap returned {len(raw_pois)} raw POIs but 0 parsed POIs for keyword '{keywords}'. "
                    f"First raw POI: {_truncate_raw_result(raw_pois[0] if raw_pois else raw_text)}"
                )
            return [], f"AMap MCP returned unparseable result for keyword '{keywords}': {_truncate_raw_result(raw_text)}"
        except Exception as exc:
            print(f"[AMAP] POI search failed: {exc}")
            return [], f"AMap POI search failed for keyword '{keywords}': {exc}"

    def get_weather(self, city: str) -> list[WeatherInfo]:
        try:
            result = self.mcp_tool.run(
                {
                    "action": "call_tool",
                    "tool_name": "maps_weather",
                    "arguments": {"city": city},
                }
            )
            payload = _normalize_mcp_result(result)
            weather = _extract_weather_list(payload)
            return weather
        except Exception as exc:
            print(f"[AMAP] 天气查询失败: {exc}")
            return []

    def plan_route(
        self,
        origin_address: str,
        destination_address: str,
        origin_city: Optional[str] = None,
        destination_city: Optional[str] = None,
        route_type: str = "walking",
    ) -> dict[str, Any]:
        """
        规划路线。

        返回字段兼容 RouteInfo:
        - distance: km
        - duration: 分钟
        - route_type
        - description
        """
        tool_map = {
            "walking": "maps_direction_walking_by_address",
            "driving": "maps_direction_driving_by_address",
            "transit": "maps_direction_transit_integrated_by_address",
        }
        tool_name = tool_map.get(route_type, "maps_direction_walking_by_address")
        arguments: dict[str, Any] = {
            "origin_address": origin_address,
            "destination_address": destination_address,
        }
        if origin_city:
            arguments["origin_city"] = origin_city
        if destination_city:
            arguments["destination_city"] = destination_city

        try:
            result = self.mcp_tool.run(
                {
                    "action": "call_tool",
                    "tool_name": tool_name,
                    "arguments": arguments,
                }
            )

            raw_text = str(result)
            payload = _normalize_mcp_result(result)
            duration_minutes = _extract_duration_minutes(payload, raw_text)
            distance_km = _extract_distance_km(payload, raw_text)
            return {
                "distance": distance_km,
                "duration": duration_minutes,
                "route_type": route_type,
                "description": f"{route_type} route from {origin_address} to {destination_address}",
                "raw": payload if payload else raw_text,
            }
        except Exception as exc:
            print(f"[AMAP] 路线规划失败: {exc}")
            return {
                "distance": 0.0,
                "duration": 0,
                "route_type": route_type,
                "description": "route unavailable",
            }

    def geocode(self, address: str, city: Optional[str] = None) -> Optional[Location]:
        try:
            arguments: dict[str, Any] = {"address": address}
            if city:
                arguments["city"] = city
            result = self.mcp_tool.run(
                {
                    "action": "call_tool",
                    "tool_name": "maps_geo",
                    "arguments": arguments,
                }
            )
            payload = _normalize_mcp_result(result)
            return _extract_location(payload)
        except Exception as exc:
            print(f"[AMAP] 地理编码失败: {exc}")
            return None

    def get_poi_detail(self, poi_id: str) -> dict[str, Any]:
        try:
            result = self.mcp_tool.run(
                {
                    "action": "call_tool",
                    "tool_name": "maps_search_detail",
                    "arguments": {"id": poi_id},
                }
            )
            payload = _normalize_mcp_result(result)
            return payload if payload else {"raw": str(result)}
        except Exception as exc:
            print(f"[AMAP] POI 详情查询失败: {exc}")
            return {}


def get_amap_service() -> AmapService:
    """获取 AmapService 单例。"""
    global _amap_service
    if _amap_service is None:
        _amap_service = AmapService()
    return _amap_service


def _normalize_mcp_result(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        return result
    if isinstance(result, list):
        return {"data": result}

    raw = str(result)
    json_match = re.search(r"\{.*\}", raw, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group())
            if isinstance(data, dict):
                return data
            if isinstance(data, list):
                return {"data": data}
        except Exception:
            pass
    return {}


def _truncate_raw_result(raw_text: str, limit: int = 500) -> str:
    text = " ".join(str(raw_text or "").split())
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def _extract_raw_poi_items(payload: dict[str, Any]) -> list[Any]:
    return _find_first_list(payload, {"pois", "data", "results"}) or []


def _extract_poi_list(payload: dict[str, Any]) -> list[POIInfo]:
    items = _extract_raw_poi_items(payload)
    pois: list[POIInfo] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        location = _extract_location(item) or Location(longitude=0.0, latitude=0.0)
        try:
            pois.append(
                POIInfo(
                    id=str(item.get("id") or item.get("poi_id") or ""),
                    name=name,
                    type=str(item.get("type") or ""),
                    address=str(item.get("address") or ""),
                    location=location,
                    tel=str(item.get("tel") or "") or None,
                )
            )
        except Exception:
            continue
    return pois


def _extract_weather_list(payload: dict[str, Any]) -> list[WeatherInfo]:
    items = _find_first_list(payload, {"forecasts", "lives", "data", "results"}) or []
    weather_list: list[WeatherInfo] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            weather_list.append(
                WeatherInfo(
                    date=str(item.get("date") or ""),
                    day_weather=str(item.get("dayweather") or item.get("day_weather") or ""),
                    night_weather=str(item.get("nightweather") or item.get("night_weather") or ""),
                    day_temp=item.get("daytemp") or item.get("day_temp") or 0,
                    night_temp=item.get("nighttemp") or item.get("night_temp") or 0,
                    wind_direction=str(item.get("daywind") or item.get("wind_direction") or ""),
                    wind_power=str(item.get("daypower") or item.get("wind_power") or ""),
                )
            )
        except Exception:
            continue
    return weather_list


def _extract_location(payload: dict[str, Any]) -> Optional[Location]:
    location = payload.get("location")
    if isinstance(location, str) and "," in location:
        lng_text, lat_text = re.split(r"\s*,\s*", location.strip(), maxsplit=1)
        try:
            return Location(longitude=float(lng_text), latitude=float(lat_text))
        except (TypeError, ValueError):
            return None

    if isinstance(location, dict):
        lng = location.get("longitude") or location.get("lng") or location.get("lon") or location.get("x")
        lat = location.get("latitude") or location.get("lat") or location.get("y")
        try:
            if lng is not None and lat is not None:
                return Location(longitude=float(lng), latitude=float(lat))
        except (TypeError, ValueError):
            return None

    lng = (
        payload.get("longitude")
        or payload.get("lng")
        or payload.get("lon")
        or payload.get("x")
        or payload.get("entr_location")
    )
    lat = payload.get("latitude") or payload.get("lat") or payload.get("y")
    if isinstance(lng, str) and "," in lng and lat is None:
        return _extract_location({"location": lng})
    try:
        if lng is not None and lat is not None:
            return Location(longitude=float(lng), latitude=float(lat))
    except (TypeError, ValueError):
        return None
    return None


def _extract_duration_minutes(payload: dict[str, Any], raw_text: str) -> int:
    value = _find_first_numeric_by_keys(payload, {"duration", "duration_sec", "duration_seconds", "time", "耗时"})
    if value is None:
        value = _extract_number_from_text(raw_text, [r"duration[\"']?\s*[:=]\s*(\d+)", r"耗时[^\d]*(\d+)"])
    if value is None:
        return 0
    if value >= 300:
        return max(1, int(round(value / 60)))
    return int(round(value))


def _extract_distance_km(payload: dict[str, Any], raw_text: str) -> float:
    value = _find_first_numeric_by_keys(payload, {"distance", "distance_m", "distance_meter", "距离"})
    if value is None:
        value = _extract_number_from_text(raw_text, [r"distance[\"']?\s*[:=]\s*(\d+)", r"距离[^\d]*(\d+)"])
    if value is None:
        return 0.0
    if value > 50:
        return round(float(value) / 1000.0, 2)
    return round(float(value), 2)


def _find_first_list(data: Any, candidate_keys: set[str]) -> list[Any] | None:
    if isinstance(data, dict):
        for key, value in data.items():
            if str(key).lower() in {item.lower() for item in candidate_keys} and isinstance(value, list):
                return value
            nested = _find_first_list(value, candidate_keys)
            if nested is not None:
                return nested
    elif isinstance(data, list):
        for item in data:
            nested = _find_first_list(item, candidate_keys)
            if nested is not None:
                return nested
    return None


def _find_first_numeric_by_keys(data: Any, candidate_keys: set[str]) -> float | None:
    lowered = {item.lower() for item in candidate_keys}
    if isinstance(data, dict):
        for key, value in data.items():
            if str(key).lower() in lowered:
                numeric = _to_float(value)
                if numeric is not None:
                    return numeric
            nested = _find_first_numeric_by_keys(value, candidate_keys)
            if nested is not None:
                return nested
    elif isinstance(data, list):
        for item in data:
            nested = _find_first_numeric_by_keys(item, candidate_keys)
            if nested is not None:
                return nested
    return None


def _extract_number_from_text(raw_text: str, patterns: list[str]) -> float | None:
    for pattern in patterns:
        match = re.search(pattern, raw_text, re.IGNORECASE)
        if not match:
            continue
        numeric = _to_float(match.group(1))
        if numeric is not None:
            return numeric
    return None


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
