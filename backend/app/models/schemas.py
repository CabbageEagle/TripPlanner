"""旅行规划相关的数据模型定义。"""

from typing import Dict, List, Optional, Union

from pydantic import BaseModel, Field, field_validator


class TripRequest(BaseModel):
    """旅行规划请求。"""

    city: str = Field(..., description="目的地城市", example="北京")
    start_date: str = Field(..., description="开始日期 YYYY-MM-DD", example="2025-06-01")
    end_date: str = Field(..., description="结束日期 YYYY-MM-DD", example="2025-06-03")
    travel_days: int = Field(..., description="旅行天数", ge=1, le=30, example=3)
    transportation: str = Field(..., description="交通方式偏好", example="公共交通")
    accommodation: str = Field(..., description="住宿偏好", example="经济型酒店")
    preferences: List[str] = Field(default_factory=list, description="旅行偏好标签", example=["历史文化", "美食"])
    free_text_input: Optional[str] = Field(default="", description="额外要求", example="希望多安排一些博物馆")

    max_budget: Optional[int] = Field(default=None, description="总预算上限", gt=0, example=3000)
    budget_per_day: Optional[int] = Field(default=None, description="每日预算上限", gt=0, example=1000)
    budget_breakdown: Optional[Dict[str, int]] = Field(
        default=None,
        description="预算分配",
        example={"attractions": 500, "meals": 300, "hotels": 400, "transportation": 200},
    )

    daily_start_time: Optional[str] = Field(default="09:00", description="每日开始时间 HH:MM", example="09:00")
    daily_end_time: Optional[str] = Field(default="21:00", description="每日结束时间 HH:MM", example="21:00")
    max_walking_time: Optional[int] = Field(default=30, description="单次最大步行时长（分钟）", example=30)
    min_rest_time: Optional[int] = Field(default=15, description="景点间最小休息时间（分钟）", example=15)

    avoid_rush_hour: Optional[bool] = Field(default=False, description="是否避开高峰期", example=False)
    max_attractions_per_day: Optional[int] = Field(default=4, description="每天最多景点数", example=4)

    @field_validator("max_budget")
    @classmethod
    def validate_budget(cls, value: Optional[int]) -> Optional[int]:
        if value is not None and value < 500:
            raise ValueError("预算过低，建议至少为 500")
        return value

    @field_validator("budget_per_day")
    @classmethod
    def validate_daily_budget(cls, value: Optional[int], info):
        if value is None:
            return value
        max_budget = info.data.get("max_budget")
        travel_days = info.data.get("travel_days")
        if max_budget and travel_days and value * travel_days > max_budget:
            raise ValueError("每日预算乘以天数不能超过总预算")
        return value


class POISearchRequest(BaseModel):
    keywords: str = Field(..., description="POI 搜索关键词", example="故宫")
    city: str = Field(..., description="城市", example="北京")
    citylimit: bool = Field(default=True, description="是否限制在城市范围内")


class RouteRequest(BaseModel):
    origin_address: str = Field(..., description="起点地址")
    destination_address: str = Field(..., description="终点地址")
    origin_city: Optional[str] = Field(default=None, description="起点城市")
    destination_city: Optional[str] = Field(default=None, description="终点城市")
    route_type: str = Field(default="walking", description="路线类型：walking / driving / transit")


class Location(BaseModel):
    longitude: float = Field(..., description="经度")
    latitude: float = Field(..., description="纬度")


class Attraction(BaseModel):
    name: str = Field(..., description="景点名称")
    address: str = Field(..., description="景点地址")
    location: Location = Field(..., description="景点位置")
    visit_duration: int = Field(..., description="建议游览时长（分钟）")
    description: str = Field(..., description="景点描述")
    category: Optional[str] = Field(default="景点", description="景点分类")
    rating: Optional[float] = Field(default=None, description="评分")
    photos: Optional[List[str]] = Field(default_factory=list, description="景点图片列表")
    poi_id: Optional[str] = Field(default="", description="POI ID")
    image_url: Optional[str] = Field(default=None, description="主图地址")
    ticket_price: int = Field(default=0, description="门票价格")
    opening_hours: Optional[str] = Field(default=None, description="开放时间")
    visit_start_time: Optional[str] = Field(default=None, description="建议到达时间")
    visit_end_time: Optional[str] = Field(default=None, description="建议离开时间")


class Meal(BaseModel):
    type: str = Field(..., description="餐食类型")
    name: str = Field(..., description="餐食名称")
    address: Optional[str] = Field(default=None, description="餐厅地址")
    location: Optional[Location] = Field(default=None, description="餐厅位置")
    description: Optional[str] = Field(default=None, description="餐食描述")
    estimated_cost: int = Field(default=0, description="预估花费")


class Hotel(BaseModel):
    name: str = Field(..., description="酒店名称")
    address: str = Field(default="", description="酒店地址")
    location: Optional[Location] = Field(default=None, description="酒店位置")
    price_range: str = Field(default="", description="价格区间")
    rating: str = Field(default="", description="评分")
    distance: str = Field(default="", description="距离景点情况")
    type: str = Field(default="", description="酒店类型")
    estimated_cost: int = Field(default=0, description="预估住宿费用")


class TimelineItem(BaseModel):
    start_time: str = Field(..., description="开始时间 HH:MM")
    end_time: str = Field(..., description="结束时间 HH:MM")
    activity_type: str = Field(..., description="活动类型")
    activity_name: str = Field(..., description="活动名称")
    duration: int = Field(..., description="持续时长（分钟）")
    location: Optional[Location] = Field(default=None, description="活动位置")
    cost: Optional[int] = Field(default=0, description="活动费用")


class Conflict(BaseModel):
    conflict_type: str = Field(..., description="冲突类型")
    severity: str = Field(..., description="冲突严重程度")
    description: str = Field(..., description="冲突描述")
    affected_items: List[str] = Field(default_factory=list, description="受影响项目")
    day_index: Optional[int] = Field(default=None, description="受影响的天数索引")


class BudgetUsage(BaseModel):
    total_budget: int = Field(..., description="总预算")
    used_budget: int = Field(..., description="已使用预算")
    remaining_budget: int = Field(..., description="剩余预算")
    breakdown: Dict[str, int] = Field(default_factory=dict, description="预算使用明细")
    over_budget: bool = Field(..., description="是否超预算")
    over_budget_amount: int = Field(default=0, description="超预算金额")


class DayPlan(BaseModel):
    date: str = Field(..., description="日期 YYYY-MM-DD")
    day_index: int = Field(..., description="第几天，从 0 开始")
    description: str = Field(..., description="当日行程描述")
    transportation: str = Field(..., description="交通方式")
    accommodation: str = Field(..., description="住宿偏好")
    hotel: Optional[Hotel] = Field(default=None, description="推荐酒店")
    attractions: List[Attraction] = Field(default_factory=list, description="当日景点列表")
    meals: List[Meal] = Field(default_factory=list, description="当日餐饮列表")
    total_cost: Optional[int] = Field(default=0, description="当日总花费")
    total_duration: Optional[int] = Field(default=0, description="当日总时长（分钟）")
    timeline: Optional[List[TimelineItem]] = Field(default=None, description="详细时间线")


class WeatherInfo(BaseModel):
    date: str = Field(..., description="日期 YYYY-MM-DD")
    day_weather: str = Field(default="", description="白天天气")
    night_weather: str = Field(default="", description="夜间天气")
    day_temp: Union[int, str] = Field(default=0, description="白天气温")
    night_temp: Union[int, str] = Field(default=0, description="夜间气温")
    wind_direction: str = Field(default="", description="风向")
    wind_power: str = Field(default="", description="风力")

    @field_validator("day_temp", "night_temp", mode="before")
    @classmethod
    def parse_temperature(cls, value: Union[int, str]) -> int:
        if isinstance(value, str):
            cleaned = value.replace("°C", "").replace("℃", "").replace("°", "").strip()
            try:
                return int(cleaned)
            except ValueError:
                return 0
        return int(value)


class Budget(BaseModel):
    total_attractions: int = Field(default=0, description="景点总花费")
    total_hotels: int = Field(default=0, description="酒店总花费")
    total_meals: int = Field(default=0, description="餐饮总花费")
    total_transportation: int = Field(default=0, description="交通总花费")
    total: int = Field(default=0, description="总花费")


class TripPlan(BaseModel):
    city: str = Field(..., description="目的地城市")
    start_date: str = Field(..., description="开始日期")
    end_date: str = Field(..., description="结束日期")
    days: List[DayPlan] = Field(..., description="每日行程")
    weather_info: List[WeatherInfo] = Field(default_factory=list, description="天气信息")
    overall_suggestions: str = Field(..., description="整体建议")
    budget: Optional[Budget] = Field(default=None, description="预算汇总")
    budget_usage: Optional[BudgetUsage] = Field(default=None, description="预算使用情况")
    time_conflicts: Optional[List[Conflict]] = Field(default=None, description="时间冲突")
    warnings: Optional[List[str]] = Field(default=None, description="警告信息")


class TripPlanResponse(BaseModel):
    success: bool = Field(..., description="是否成功")
    message: str = Field(default="", description="返回消息")
    plan_id: Optional[str] = Field(default=None, description="已保存的行程 ID")
    data: Optional[TripPlan] = Field(default=None, description="旅行计划数据")


class TripPlanUpdateRequest(BaseModel):
    data: TripPlan = Field(..., description="更新后的完整旅行计划")
    note: Optional[str] = Field(default=None, description="可选的更新备注")


class POIInfo(BaseModel):
    id: str = Field(..., description="POI ID")
    name: str = Field(..., description="POI 名称")
    type: str = Field(..., description="POI 类型")
    address: str = Field(..., description="POI 地址")
    location: Location = Field(..., description="POI 位置")
    tel: Optional[str] = Field(default=None, description="联系电话")


class POISearchResponse(BaseModel):
    success: bool = Field(..., description="是否成功")
    message: str = Field(default="", description="返回消息")
    data: List[POIInfo] = Field(default_factory=list, description="POI 列表")


class RouteInfo(BaseModel):
    distance: float = Field(..., description="距离")
    duration: int = Field(..., description="耗时")
    route_type: str = Field(..., description="路线类型")
    description: str = Field(..., description="路线描述")


class RouteResponse(BaseModel):
    success: bool = Field(..., description="是否成功")
    message: str = Field(default="", description="返回消息")
    data: Optional[RouteInfo] = Field(default=None, description="路线信息")


class WeatherResponse(BaseModel):
    success: bool = Field(..., description="是否成功")
    message: str = Field(default="", description="返回消息")
    data: List[WeatherInfo] = Field(default_factory=list, description="天气信息")


class ErrorResponse(BaseModel):
    success: bool = Field(default=False, description="是否成功")
    message: str = Field(..., description="错误消息")
    error_code: Optional[str] = Field(default=None, description="错误代码")
