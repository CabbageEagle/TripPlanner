# 时间冲突与预算限制功能说明

## 📋 功能概述

实现了智能旅行规划系统的两大核心验证功能：
1. **时间冲突检测** - 确保行程时间合理，无重叠
2. **预算限制检查** - 确保费用在预算范围内

## 🎯 新增功能

### 1. TripRequest 新增字段

#### 预算控制
```python
max_budget: Optional[int]              # 最大总预算（元）
budget_per_day: Optional[int]          # 每日预算限制（元）
budget_breakdown: Optional[Dict[str, int]]  # 预算分配
```

**示例：**
```json
{
  "max_budget": 3000,
  "budget_per_day": 1000,
  "budget_breakdown": {
    "attractions": 500,
    "meals": 300,
    "hotels": 400,
    "transportation": 200
  }
}
```

#### 时间控制
```python
daily_start_time: Optional[str]        # 每日开始时间 "09:00"
daily_end_time: Optional[str]          # 每日结束时间 "21:00"
max_walking_time: Optional[int]        # 最大步行时间（分钟）
min_rest_time: Optional[int]           # 最小休息时间（分钟）
```

**示例：**
```json
{
  "daily_start_time": "09:00",
  "daily_end_time": "21:00",
  "max_walking_time": 30,
  "min_rest_time": 15
}
```

#### 其他限制
```python
avoid_rush_hour: Optional[bool]        # 避开高峰期
max_attractions_per_day: Optional[int] # 每天最多景点数
```

### 2. 响应模型增强

#### Attraction 新增字段
```python
opening_hours: Optional[str]           # 开放时间
visit_start_time: Optional[str]        # 建议到达时间
visit_end_time: Optional[str]          # 建议离开时间
```

#### DayPlan 新增字段
```python
total_cost: Optional[int]              # 当日总费用
total_duration: Optional[int]          # 当日总时长（分钟）
timeline: Optional[List[TimelineItem]] # 详细时间线
```

#### TripPlan 新增字段
```python
budget_usage: Optional[BudgetUsage]    # 预算使用情况
time_conflicts: Optional[List[Conflict]] # 时间冲突列表
warnings: Optional[List[str]]          # 警告信息
```

### 3. 新增数据模型

#### TimelineItem - 时间线项目
```python
class TimelineItem(BaseModel):
    start_time: str          # 开始时间 "09:00"
    end_time: str            # 结束时间 "11:00"
    activity_type: str       # attraction/meal/travel/rest
    activity_name: str       # 活动名称
    duration: int            # 持续时间（分钟）
    location: Optional[Location]
    cost: Optional[int]
```

#### Conflict - 冲突信息
```python
class Conflict(BaseModel):
    conflict_type: str       # time/budget/capacity
    severity: str            # critical/warning/info
    description: str         # 冲突描述
    affected_items: List[str]  # 受影响项目
    day_index: Optional[int]
```

#### BudgetUsage - 预算使用情况
```python
class BudgetUsage(BaseModel):
    total_budget: int        # 总预算
    used_budget: int         # 已用预算
    remaining_budget: int    # 剩余预算
    breakdown: Dict[str, int]  # 分类明细
    over_budget: bool        # 是否超预算
    over_budget_amount: int  # 超预算金额
```

## 🔧 验证逻辑

### 时间冲突检测

1. **景点数量检查**
   - 检查每天景点数是否超过 `max_attractions_per_day`
   - 超过则产生 warning 级别冲突

2. **时间线生成**
   - 按照 早餐 → 景点 → 午餐 → 景点 → 晚餐 顺序
   - 自动计算每个活动的起止时间
   - 考虑景点间移动时间（默认20分钟）

3. **时间重叠检查**
   - 检测相邻活动是否有时间重叠
   - 产生 critical 级别冲突

4. **时间范围检查**
   - 检查行程是否在 daily_start_time ~ daily_end_time 内
   - 超时产生 warning 级别冲突

### 预算限制检查

1. **费用计算**
   ```
   景点费用 = Σ ticket_price
   餐饮费用 = Σ estimated_cost (meals)
   酒店费用 = Σ estimated_cost (hotels)
   交通费用 = 天数 × 50元（估算）
   ```

2. **每日预算检查**
   - 每天费用 vs budget_per_day
   - 超过产生 warning 级别冲突

3. **总预算检查**
   - 总费用 vs max_budget
   - 超过产生 critical 级别冲突

4. **预算使用分析**
   - 生成详细的费用分类明细
   - 计算剩余预算
   - 标记是否超预算

## 🚀 集成到工作流

### 在 graph_nodes.py 中导入
```python
from .validation_nodes import (
    check_time_conflicts_node,
    check_budget_limits_node
)
```

### 在 trip_planner_agent_langgraph.py 中添加节点
```python
# 添加验证节点
workflow.add_node("check_time", check_time_conflicts_node)
workflow.add_node("check_budget", check_budget_limits_node)

# 在 verify_plan 之后添加
workflow.add_edge("verify_plan", "check_time")
workflow.add_edge("check_time", "check_budget")

# 条件边：根据冲突严重程度决定修复或结束
workflow.add_conditional_edges(
    "check_budget",
    should_fix_conflicts,
    {
        "fix_plan": "fix_plan",
        "END": END
    }
)
```

### 添加冲突修复路由
```python
def should_fix_conflicts(state: TripPlannerState) -> Literal["fix_plan", "END"]:
    """根据冲突决定是否修复"""
    conflicts = state.get("time_conflicts", [])
    
    if not conflicts:
        return "END"
    
    # 检查是否有严重冲突
    critical_conflicts = [c for c in conflicts if c.get("severity") == "critical"]
    
    if critical_conflicts:
        print(f"🔧 发现 {len(critical_conflicts)} 个严重冲突，需要修复")
        return "fix_plan"
    else:
        print(f"⚠️  仅有 {len(conflicts)} 个轻微问题，可以接受")
        return "END"
```

## 📊 响应示例

### 成功响应（有轻微警告）
```json
{
  "success": true,
  "data": {
    "city": "北京",
    "days": [...],
    "budget_usage": {
      "total_budget": 3000,
      "used_budget": 2800,
      "remaining_budget": 200,
      "breakdown": {
        "attractions": 500,
        "meals": 480,
        "hotels": 1200,
        "transportation": 620
      },
      "over_budget": false,
      "over_budget_amount": 0
    },
    "time_conflicts": [
      {
        "conflict_type": "time",
        "severity": "warning",
        "description": "第2天行程结束时间(21:30)超过限制(21:00)",
        "affected_items": ["晚餐"],
        "day_index": 1
      }
    ],
    "warnings": ["第2天行程略微超时，建议提前30分钟开始"]
  }
}
```

### 超预算响应（需要修复）
```json
{
  "time_conflicts": [
    {
      "conflict_type": "budget",
      "severity": "critical",
      "description": "总费用(3500元)超过预算限制(3000元)",
      "affected_items": ["总预算"]
    },
    {
      "conflict_type": "budget",
      "severity": "warning",
      "description": "第1天费用(1200元)超过每日预算(1000元)",
      "affected_items": ["第1天"],
      "day_index": 0
    }
  ],
  "budget_usage": {
    "total_budget": 3000,
    "used_budget": 3500,
    "remaining_budget": 0,
    "over_budget": true,
    "over_budget_amount": 500
  }
}
```

## ✅ 使用建议

1. **前端表单增强**
   - 添加预算输入框（总预算、每日预算）
   - 添加时间范围选择（开始时间、结束时间）
   - 添加其他限制选项（最大景点数等）

2. **结果展示优化**
   - 显示预算使用饼图或进度条
   - 显示时间线甘特图
   - 高亮显示冲突和警告信息

3. **交互优化**
   - 超预算时给出降低费用的建议
   - 时间冲突时提供调整方案
   - 允许用户调整优先级

4. **智能调整**
   - 超预算时自动选择更便宜的替代方案
   - 时间紧张时减少景点或缩短游览时间
   - 根据反馈迭代优化

## 🎯 下一步开发

- [ ] 添加实时交通时间估算（调用地图API）
- [ ] 支持多种交通方式切换
- [ ] 景点开放时间验证
- [ ] 节假日价格调整
- [ ] 个性化预算建议
- [ ] 可视化时间线编辑器
