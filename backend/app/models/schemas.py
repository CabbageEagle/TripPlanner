"""数据模型定义"""

from typing import List, Optional, Union, Dict
from pydantic import BaseModel, Field, field_validator
from datetime import date


# ============ 请求模型 ============

class TripRequest(BaseModel):
    """旅行规划请求"""
    # 基本信息
    city: str = Field(..., description="目的地城市", example="北京")
    start_date: str = Field(..., description="开始日期 YYYY-MM-DD", example="2025-06-01")
    end_date: str = Field(..., description="结束日期 YYYY-MM-DD", example="2025-06-03")
    travel_days: int = Field(..., description="旅行天数", ge=1, le=30, example=3)
    transportation: str = Field(..., description="交通方式", example="公共交通")
    accommodation: str = Field(..., description="住宿偏好", example="经济型酒店")
    preferences: List[str] = Field(default=[], description="旅行偏好标签", example=["历史文化", "美食"])
    free_text_input: Optional[str] = Field(default="", description="额外要求", example="希望多安排一些博物馆")
    
    # 预算限制（可选，建议填写）
    max_budget: Optional[int] = Field(
        default=None, 
        description="最大总预算（元）- 建议填写，用于控制整体费用", 
        example=3000,
        gt=0
    )
    budget_per_day: Optional[int] = Field(
        default=None, 
        description="每日预算限制（元）- 可选，不填则自动分配", 
        example=1000,
        gt=0
    )
    budget_breakdown: Optional[Dict[str, int]] = Field(
        default=None, 
        description="预算分配 {类型: 金额}",
        example={"attractions": 500, "meals": 300, "hotels": 400, "transportation": 200}
    )
    
    # 时间限制
    daily_start_time: Optional[str] = Field(default="09:00", description="每日开始时间 HH:MM", example="09:00")
    daily_end_time: Optional[str] = Field(default="21:00", description="每日结束时间 HH:MM", example="21:00")
    max_walking_time: Optional[int] = Field(default=30, description="单次最大步行时间（分钟）", example=30)
    min_rest_time: Optional[int] = Field(default=15, description="景点间最小休息时间（分钟）", example=15)
    
    # 其他限制
    avoid_rush_hour: Optional[bool] = Field(default=False, description="避开高峰期", example=False)
    max_attractions_per_day: Optional[int] = Field(default=4, description="每天最多景点数", example=4)
    
    class Config:
        json_schema_extra = {
            "example": {
                "city": "北京",
                "start_date": "2025-06-01",
                "end_date": "2025-06-03",
                "travel_days": 3,
                "transportation": "公共交通",
                "accommodation": "经济型酒店",
                "preferences": ["历史文化", "美食"],
                "free_text_input": "希望多安排一些博物馆",
                "max_budget": 3000,
                "daily_start_time": "09:00",
                "daily_end_time": "21:00",
                "max_walking_time": 30,
                "min_rest_time": 15,
                "avoid_rush_hour": False,
                "max_attractions_per_day": 4
            }
        }
    
    @field_validator('max_budget')
    @classmethod
    def validate_budget(cls, v):
        """验证预算合理性"""
        if v is not None:
            if v <= 0:
                raise ValueError("预算必须大于0")
            if v < 500:
                raise ValueError("预算过低，建议至少500元")
        return v
    
    @field_validator('budget_per_day')
    @classmethod
    def validate_daily_budget(cls, v, info):
        """验证每日预算"""
        if v is not None:
            if v <= 0:
                raise ValueError("每日预算必须大于0")
            # 如果有总预算，检查每日预算是否合理
            max_budget = info.data.get('max_budget')
            travel_days = info.data.get('travel_days')
            if max_budget and travel_days and v * travel_days > max_budget:
                raise ValueError(f"每日预算({v}元) × 天数({travel_days}) 超过总预算({max_budget}元)")
        return v


class POISearchRequest(BaseModel):
    """POI搜索请求"""
    keywords: str = Field(..., description="搜索关键词", example="故宫")
    city: str = Field(..., description="城市", example="北京")
    citylimit: bool = Field(default=True, description="是否限制在城市范围内")


class RouteRequest(BaseModel):
    """路线规划请求"""
    origin_address: str = Field(..., description="起点地址", example="北京市朝阳区阜通东大街6号")
    destination_address: str = Field(..., description="终点地址", example="北京市海淀区上地十街10号")
    origin_city: Optional[str] = Field(default=None, description="起点城市")
    destination_city: Optional[str] = Field(default=None, description="终点城市")
    route_type: str = Field(default="walking", description="路线类型: walking/driving/transit")


# ============ 响应模型 ============

class Location(BaseModel):
    """地理位置"""
    longitude: float = Field(..., description="经度")
    latitude: float = Field(..., description="纬度")


class Attraction(BaseModel):
    """景点信息"""
    name: str = Field(..., description="景点名称")
    address: str = Field(..., description="地址")
    location: Location = Field(..., description="经纬度坐标")
    visit_duration: int = Field(..., description="建议游览时间(分钟)")
    description: str = Field(..., description="景点描述")
    category: Optional[str] = Field(default="景点", description="景点类别")
    rating: Optional[float] = Field(default=None, description="评分")
    photos: Optional[List[str]] = Field(default_factory=list, description="景点图片URL列表")
    poi_id: Optional[str] = Field(default="", description="POI ID")
    image_url: Optional[str] = Field(default=None, description="图片URL")
    ticket_price: int = Field(default=0, description="门票价格(元)")
    
    # 时间相关字段
    opening_hours: Optional[str] = Field(default=None, description="开放时间", example="09:00-17:00")
    visit_start_time: Optional[str] = Field(default=None, description="建议到达时间", example="10:00")
    visit_end_time: Optional[str] = Field(default=None, description="建议离开时间", example="12:00")


class Meal(BaseModel):
    """餐饮信息"""
    type: str = Field(..., description="餐饮类型: breakfast/lunch/dinner/snack")
    name: str = Field(..., description="餐饮名称")
    address: Optional[str] = Field(default=None, description="地址")
    location: Optional[Location] = Field(default=None, description="经纬度坐标")
    description: Optional[str] = Field(default=None, description="描述")
    estimated_cost: int = Field(default=0, description="预估费用(元)")


class Hotel(BaseModel):
    """酒店信息"""
    name: str = Field(..., description="酒店名称")
    address: str = Field(default="", description="酒店地址")
    location: Optional[Location] = Field(default=None, description="酒店位置")
    price_range: str = Field(default="", description="价格范围")
    rating: str = Field(default="", description="评分")
    distance: str = Field(default="", description="距离景点距离")
    type: str = Field(default="", description="酒店类型")
    estimated_cost: int = Field(default=0, description="预估费用(元/晚)")


class TimelineItem(BaseModel):
    """时间线项目"""
    start_time: str = Field(..., description="开始时间 HH:MM", example="09:00")
    end_time: str = Field(..., description="结束时间 HH:MM", example="11:00")
    activity_type: str = Field(..., description="活动类型", example="attraction")
    activity_name: str = Field(..., description="活动名称", example="故宫")
    duration: int = Field(..., description="持续时间（分钟）", example=120)
    location: Optional[Location] = Field(default=None, description="位置")
    cost: Optional[int] = Field(default=0, description="费用（元）")


class Conflict(BaseModel):
    """冲突信息"""
    conflict_type: str = Field(..., description="冲突类型: time/budget/capacity", example="time")
    severity: str = Field(..., description="严重程度: critical/warning/info", example="warning")
    description: str = Field(..., description="冲突描述", example="景点A与景点B时间重叠")
    affected_items: List[str] = Field(default=[], description="受影响的项目", example=["景点A", "景点B"])
    day_index: Optional[int] = Field(default=None, description="影响的日期索引")


class BudgetUsage(BaseModel):
    """预算使用情况"""
    total_budget: int = Field(..., description="总预算（元）", example=3000)
    used_budget: int = Field(..., description="已用预算（元）", example=2800)
    remaining_budget: int = Field(..., description="剩余预算（元）", example=200)
    breakdown: Dict[str, int] = Field(
        default={}, 
        description="分类使用情况",
        example={"attractions": 500, "meals": 300, "hotels": 400, "transportation": 200}
    )
    over_budget: bool = Field(..., description="是否超预算", example=False)
    over_budget_amount: int = Field(default=0, description="超预算金额（元）", example=0)


class DayPlan(BaseModel):
    """单日行程"""
    date: str = Field(..., description="日期 YYYY-MM-DD")
    day_index: int = Field(..., description="第几天(从0开始)")
    description: str = Field(..., description="当日行程描述")
    transportation: str = Field(..., description="交通方式")
    accommodation: str = Field(..., description="住宿")
    hotel: Optional[Hotel] = Field(default=None, description="推荐酒店")
    attractions: List[Attraction] = Field(default=[], description="景点列表")
    meals: List[Meal] = Field(default=[], description="餐饮列表")
    
    # 新增字段
    total_cost: Optional[int] = Field(default=0, description="当日总费用（元）")
    total_duration: Optional[int] = Field(default=0, description="当日总时长（分钟）")
    timeline: Optional[List[TimelineItem]] = Field(default=None, description="详细时间线")


class WeatherInfo(BaseModel):
    """天气信息"""
    date: str = Field(..., description="日期 YYYY-MM-DD")
    day_weather: str = Field(default="", description="白天天气")
    night_weather: str = Field(default="", description="夜间天气")
    day_temp: Union[int, str] = Field(default=0, description="白天温度")
    night_temp: Union[int, str] = Field(default=0, description="夜间温度")
    wind_direction: str = Field(default="", description="风向")
    wind_power: str = Field(default="", description="风力")

    @field_validator('day_temp', 'night_temp', mode='before')
    @classmethod
    def parse_temperature(cls, v):
        """解析温度,移除°C等单位"""
        if isinstance(v, str):
            # 移除°C, ℃等单位符号
            v = v.replace('°C', '').replace('℃', '').replace('°', '').strip()
            try:
                return int(v)
            except ValueError:
                return 0
        return v


class Budget(BaseModel):
    """预算信息"""
    total_attractions: int = Field(default=0, description="景点门票总费用")
    total_hotels: int = Field(default=0, description="酒店总费用")
    total_meals: int = Field(default=0, description="餐饮总费用")
    total_transportation: int = Field(default=0, description="交通总费用")
    total: int = Field(default=0, description="总费用")


class TripPlan(BaseModel):
    """旅行计划"""
    city: str = Field(..., description="目的地城市")
    start_date: str = Field(..., description="开始日期")
    end_date: str = Field(..., description="结束日期")
    days: List[DayPlan] = Field(..., description="每日行程")
    weather_info: List[WeatherInfo] = Field(default=[], description="天气信息")
    overall_suggestions: str = Field(..., description="总体建议")
    budget: Optional[Budget] = Field(default=None, description="预算信息")
    
    # 新增字段
    budget_usage: Optional[BudgetUsage] = Field(default=None, description="预算使用情况")
    time_conflicts: Optional[List[Conflict]] = Field(default=None, description="时间冲突列表")
    warnings: Optional[List[str]] = Field(default=None, description="警告信息列表")


class TripPlanResponse(BaseModel):
    """旅行计划响应"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(default="", description="消息")
    data: Optional[TripPlan] = Field(default=None, description="旅行计划数据")


class POIInfo(BaseModel):
    """POI信息"""
    id: str = Field(..., description="POI ID")
    name: str = Field(..., description="名称")
    type: str = Field(..., description="类型")
    address: str = Field(..., description="地址")
    location: Location = Field(..., description="经纬度坐标")
    tel: Optional[str] = Field(default=None, description="电话")


class POISearchResponse(BaseModel):
    """POI搜索响应"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(default="", description="消息")
    data: List[POIInfo] = Field(default=[], description="POI列表")


class RouteInfo(BaseModel):
    """路线信息"""
    distance: float = Field(..., description="距离(米)")
    duration: int = Field(..., description="时间(秒)")
    route_type: str = Field(..., description="路线类型")
    description: str = Field(..., description="路线描述")


class RouteResponse(BaseModel):
    """路线规划响应"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(default="", description="消息")
    data: Optional[RouteInfo] = Field(default=None, description="路线信息")


class WeatherResponse(BaseModel):
    """天气查询响应"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(default="", description="消息")
    data: List[WeatherInfo] = Field(default=[], description="天气信息")


# ============ 错误响应 ============

class ErrorResponse(BaseModel):
    """错误响应"""
    success: bool = Field(default=False, description="是否成功")
    message: str = Field(..., description="错误消息")
    error_code: Optional[str] = Field(default=None, description="错误代码")

