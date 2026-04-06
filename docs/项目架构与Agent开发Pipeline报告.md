# HelloAgents Trip Planner
## 项目架构与 Agent 开发 Pipeline 报告

版本：v1.0  
生成日期：2026-03-23  
面向对象：研发团队、技术负责人、Agent 工程师

---

## 1. 项目目标与定位

本项目是一个“可编辑、可版本化、可记忆”的智能旅行规划系统。  
核心目标不是仅生成一次性行程，而是支持：

- 从自然语言需求到结构化多天行程的自动生成
- 旅行计划在前端可编辑，并能回传后端进行自动重排
- 将用户编辑行为沉淀为“偏好记忆”，用于后续规划质量持续提升

从工程视角看，这个系统属于“LLM 规划 + 确定性调度 + 记忆增强 + 工具调用”的混合 Agent 架构。

---

## 2. 系统总体架构

### 2.1 分层结构

系统按职责分为四层：

- 展示层（Frontend）
- 接口层（FastAPI Routes）
- Agent 编排层（LangGraph）
- 能力服务层（地图服务、排程服务、记忆服务、存储）

### 2.2 架构总览（逻辑图）

```text
[Vue3 Frontend]
    |
    | HTTP (/api/trip/*, /api/poi/*, /api/map/*)
    v
[FastAPI API Layer]
    |
    | plan / update / get
    v
[LangGraph Agent Orchestrator]
    |         |           |
    |         |           +--> [Memory Service]
    |         +--------------> [Scheduler Service]
    +------------------------> [Amap Service / MCP Tools]
    |
    v
[Plan Repository + Versioning]
```

---

## 3. 核心模块拆解

### 3.1 前端模块（Vue3 + TS）

前端职责不是“只展示结果”，而是承担用户编辑和反馈入口：

- Home 页面：收集城市、日期、预算、偏好、时间约束等输入
- Result 页面：展示日程、景点、预算、天气、冲突告警
- 编辑能力：支持景点顺序调整、景点删除、内容编辑
- 持久化：本地 sessionStorage 缓存 + planId 云端同步

前端关键工程点：

- 显示层已增加 `opening_hours / visit_start_time / visit_end_time` 字段承载排程结果
- 编辑状态下提示“时间线可能过期”，引导用户触发后端重排

### 3.2 API 模块（FastAPI）

Trip 路由承担三个关键动作：

- 生成计划：`POST /api/trip/plan`
- 读取计划：`GET /api/trip/plans/{plan_id}`
- 更新计划：`PUT /api/trip/plans/{plan_id}`

其中 `PUT` 的价值最大：它把“用户编辑”变成“可自动重排 + 可版本化保存 + 可提炼记忆”的闭环。

### 3.3 Agent 编排模块（LangGraph）

LangGraph 工作流主要节点：

1. `search_attractions`
2. `query_weather`
3. `search_hotels`
4. `plan_trip`
5. `parse_plan`
6. `schedule_plan`（新增）
7. `verify_plan`
8. `fix_plan`（按条件触发）
9. `error_handler`

关键变化：`parse_plan -> schedule_plan -> verify_plan`  
这意味着“先排程后校验”，校验依据更贴近可执行计划。

### 3.4 服务层模块

#### Amap Service

- 从“占位式返回”重构为“结构化解析”
- 统一 MCP 返回归一化：`_normalize_mcp_result`
- 增加数据提取器：POI、天气、路线时长、距离、坐标等
- 为不同 MCP 返回格式提供鲁棒解析（递归找 list/数值/正则兜底）

#### Scheduler Service（新增）

- 输入：DayPlan + ScheduleConfig
- 输出：补全后的 DayPlan（timeline、visit_start_time、visit_end_time、total_duration、total_cost）
- 规则：
  - 按营业时间约束景点访问窗口
  - 在时段内插入午餐/晚餐
  - 估算交通耗时（可选调用 MCP 路径规划）
  - 时间不足时生成 warnings，而不是硬失败

#### Memory Service

- `summarize_preferences` 从简单去重升级为“评分排序 + 冲突抑制”
- 引入评分因素：
  - memory type bonus
  - source bonus
  - 时间衰减（recency decay）
  - 检索排名因子
- 引入冲突组：节奏偏好、景点风格、住宿偏好等，避免摘要自相矛盾

#### LLM-as-Judge 评估模块（核心质量闭环）

该项目包含独立的评估子系统，不与在线 API 主链路耦合，主要用于离线质量评测与回归对比：

- 评估核心：`app/services/judge.py`
- 执行入口：`backend/run_eval.py`
- 评估结果：`backend/eval_reports/*.json`

评估能力特征：

- 支持 `llm / heuristic / auto` 三种评估模式
- 支持 `strict_llm_judge`，确保评估必须由 LLM 裁判完成
- 结构化输出多维得分与问题列表，便于自动化对比和趋势追踪
- 配置独立 `JUDGE_MODEL`，与生成模型解耦，避免评估偏置

---

## 4. 两条主 Pipeline 详解

## 4.1 生成 Pipeline（Create Plan）

```text
TripRequest
  -> LangGraph 搜索景点/天气/酒店
  -> LLM 聚合生成草案 JSON
  -> 解析为结构化 plan
  -> 排程器补全 timeline 与建议时间
  -> 结构校验与约束校验
  -> 必要时修复（fix loop）
  -> 返回 TripPlan
```

此流程的重点不是单点生成，而是“生成后工程化处理”：

- LLM 负责语义规划
- Scheduler 负责可执行时间轴
- Verify/Fix 负责结构质量与约束闭环

## 4.2 编辑 Pipeline（Edit Plan）

```text
用户在 Result 页编辑
  -> 前端 saveChanges
  -> PUT /api/trip/plans/{plan_id}
  -> 后端按天 schedule_day_plan 自动重排
  -> 保存新版本（versioned）
  -> 提取编辑记忆（preference/dislike/constraint）
  -> 返回更新后的 plan
```

这条 Pipeline 是项目最具业务价值的能力：  
它让 Agent 从“一次性回答”演进为“可持续学习的规划系统”。

## 4.3 评估 Pipeline（LLM as Judge）

```text
测试样例 / 真实样例
  -> run_eval.py 组织 case
  -> 调用 judge_trip_plan
  -> LLM 评估（或 heuristic 回退）
  -> 输出多维评分与问题项
  -> 写入 eval_report_latest + history 归档
```

这条 Pipeline 的价值是把“主观好坏”转成“可追踪指标”，用于：

- Prompt / Workflow 调整的前后对比
- 不同模型版本的质量回归
- 线上问题复盘后的离线复测

---

## 5. Agent 开发重点（工程实践）

### 5.1 重点一：LLM 与确定性模块解耦

最佳实践：

- LLM 负责“意图与语义规划”
- 确定性模块负责“时间、成本、规则可执行性”

收益：

- 减少模型幻觉导致的不可执行日程
- 易测试、易回归、易解释

### 5.2 重点二：State 先行设计

`TripPlannerState` 中新增 `schedule_applied / schedule_notes` 等字段，体现了“状态可观测、可调试、可扩展”的设计思路。

建议：

- 为每个关键节点定义输入输出契约
- 将错误和警告纳入状态字段，不只依赖日志

### 5.3 重点三：验证与修复闭环

工作流中的 `verify_plan + fix_plan` 是 Agent 产品化关键：

- 把“质量控制”从人工 review 下沉到 pipeline
- 控制修复次数与修复范围，避免无效循环

### 5.4 重点四：工具调用结果标准化

MCP 返回常常是弱结构化文本。统一归一化层可以显著降低下游复杂度：

- 标准化输入形态（dict/list/raw text）
- 统一抽取路径（递归 + key 候选 + 正则兜底）
- 抽取失败时可降级返回，不阻断主流程

### 5.5 重点五：Human-in-the-loop + 记忆沉淀

编辑行为不是“覆盖数据”，而是“新增版本 + 抽取记忆信号”。  
这是 Agent 从工具走向产品的核心分水岭。

---

## 6. 技术热点与创新点

本项目在 Agent 工程上的技术热点主要体现在以下五点：

1. **LangGraph 条件编排**
   - 多节点串联 + 条件边 + 修复循环

2. **LLM 规划与规则排程混合架构**
   - 语义生成与时间执行分离

3. **弱结构化工具输出鲁棒解析**
   - 面向真实 API 返回不稳定性的工程化处理

4. **偏好记忆评分与冲突抑制**
   - 避免记忆摘要“噪声大、矛盾多”

5. **LLM-as-Judge 质量评测体系**
   - 结构化评分 + 严格模式 + 报告归档

6. **计划版本化 + 编辑回流学习**
   - 把用户编辑转成下一次规划的学习资产

---

## 7. 当前风险与可优化方向

### 7.1 风险点

- 部分日志与告警仍偏开发态，缺统一监控看板
- 排程 warnings 在不同入口的落盘与展示策略可进一步统一
- MCP 路径规划目前默认可关闭，真实线上需要按成本与性能评估打开策略

### 7.2 优化建议

1. 引入节点级指标采集（耗时、失败率、重试率）
2. 为 `schedule_plan` 增加单元测试集（营业时间边界、跨时段插餐、超时截断）
3. 将记忆评分参数配置化并 A/B 测试
4. 把告警结构标准化（code/severity/source/suggestion）
5. 逐步接入流式可视化，展示节点执行进度

---

## 8. 结论

该项目已从“单次生成式 AI Demo”升级为“具备工程闭环的 Agent 系统原型”，其核心优势在于：

- 编排可控（LangGraph）
- 执行可落地（Scheduler）
- 反馈可学习（Memory）
- 计划可持续演进（Versioning + Edit Loop）

若继续沿“可观测、可测试、可演进”方向推进，可以较快形成面向真实业务场景的 Agent 应用能力。
