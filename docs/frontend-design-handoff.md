# 智能旅行助手前端美化交接文档

本文档面向前端工程师，用于在不破坏后端适配的前提下重新设计并美化现有前端页面。当前项目已经具备完整业务链路，设计改造应优先复用现有 Vue 3、TypeScript、Vite、Ant Design Vue、Amap JS API、html2canvas、jspdf，不新增后端实体，不改接口字段名。

## 1. 当前系统结论

项目已有两个核心路由：

- `/`：旅行需求填写页，提交后生成旅行计划。
- `/result`：旅行计划结果页，展示地图、预算、每日行程、天气、风险提醒、Agent 诊断，并支持编辑、保存、导出图片/PDF。

当前前端文件：

- `frontend/src/App.vue`：全局布局，目前存在乱码文案和较重的默认 Header/Footer。
- `frontend/src/views/Home.vue`：首页大表单，直接调用 SSE 生成接口。
- `frontend/src/views/Result.vue`：结果详情页，包含地图、侧边导航、编辑保存、导出。
- `frontend/src/services/api.ts`：接口封装，不建议改变返回结构。
- `frontend/src/types/index.ts`：前后端字段契约。

后端入口：

- `POST /api/trip/plan/stream`：推荐使用，返回 SSE 进度和最终结果。
- `POST /api/trip/plan`：非流式生成。
- `GET /api/trip/plans/{plan_id}`：按 ID 获取已保存计划。
- `PUT /api/trip/plans/{plan_id}`：保存用户编辑后的完整计划。
- `GET /api/poi/photo?name=...`：获取景点图片。
- `GET /health`、`GET /api/trip/health`：健康检查。

## 2. 设计目标

本次前端美化的目标不是做营销页，而是把系统整理成一个“旅行规划工作台”：

- 首页降低视觉噪音，让用户快速填写旅行条件。
- 结果页提高信息密度和可扫描性，尤其是每日行程、预算、地图、风险提醒。
- 保留现有后端链路、sessionStorage 缓存、planId 查询参数、编辑保存和导出能力。
- 优先解决移动端可用性，避免当前大横向布局在小屏上拥挤。
- 保持中文旅行产品语气：清晰、轻快、可信，不使用过度营销文案。

建议视觉方向：**清爽城市旅行工作台**。主色使用清澈蓝绿或湖蓝，搭配暖黄色作为重点提示色，避免继续使用大面积紫色渐变。整体应更像实用工具，而不是落地页。

## 3. 信息架构

### 首页

首页只承担一件事：收集旅行规划参数并开始生成。

建议分为四块，而不是把所有字段铺成等权重表单：

1. 基础行程：城市、日期、旅行天数。
2. 旅行方式：交通方式、住宿偏好、兴趣标签。
3. 约束条件：预算、每日时间、每日最多景点数。
4. 额外要求：自由文本和提交。

ASCII 示意：

```text
+--------------------------------------------------------------+
| 智能旅行助手                                   [健康状态可选] |
| 目的地、日期和偏好，生成可编辑的每日行程。                   |
+--------------------------------------------------------------+
| 目的地城市 [ 北京                  ]                         |
| 日期范围   [ 2026-05-01 ] - [ 2026-05-03 ]   共 3 天         |
+--------------------------------------------------------------+
| 交通方式   [公共交通] [自驾] [步行] [混合]                   |
| 住宿偏好   [经济型] [舒适型] [豪华] [民宿] [当天往返]        |
| 兴趣偏好   [历史文化] [自然风光] [美食] [购物] [艺术] [休闲] |
+--------------------------------------------------------------+
| 总预算 [ 3000 元 ]      每日预算 [ 自动分配 ]                |
| 开始 [09:00]  结束 [21:00]  每天最多景点 [4]                 |
+--------------------------------------------------------------+
| 额外要求                                                     |
| [ 想看展、少走路、不要太赶......                         ]   |
|                                             [生成旅行计划]    |
+--------------------------------------------------------------+
```

### 结果页

结果页应优先展示“用户接下来怎么走”，不要让地图或诊断信息抢走主线。

建议桌面布局：

```text
+--------------------------------------------------------------------+
| [返回]  北京 3日旅行计划                         [编辑] [导出 v]  |
| 2026-05-01 至 2026-05-03  公共交通  预算 ¥3000                    |
+--------------------+-----------------------------------------------+
| 行程导航           | 概览指标                                      |
| - 概览             | [总费用] [天气] [风险] [景点数]              |
| - 预算             +-----------------------+-----------------------+
| - 风险提醒         | 今日/每日行程         | 地图                  |
| - 第1天            | 09:00 故宫            |                       |
| - 第2天            | 12:00 午餐            |        AMap          |
| - 第3天            | 14:00 景点            |                       |
| - 天气             +-----------------------+-----------------------+
| - Agent诊断        | 景点卡片 / 酒店 / 餐饮 / 天气 / 预算明细     |
+--------------------+-----------------------------------------------+
```

移动端布局：

```text
+------------------------------+
| 北京 3日旅行计划             |
| [返回] [编辑] [导出]         |
+------------------------------+
| [概览] [每日] [地图] [预算]  |
+------------------------------+
| 总费用 / 风险 / 天气摘要     |
+------------------------------+
| 第1天  2026-05-01            |
| 09:00 故宫                   |
| 12:00 午餐                   |
| 14:00 景点                   |
+------------------------------+
| 地图                         |
+------------------------------+
```

## 4. 页面改造要求

### App.vue

- 去掉或弱化当前深色通栏 Header/Footer，避免和首页自身头图重复。
- 修复乱码文案，统一为 UTF-8 中文。
- 全局只保留必要的页面容器，不要给所有页面强行套 24px padding，结果页和首页应各自控制布局。

建议顶部栏：

- 左侧：产品名“智能旅行助手”。
- 右侧：可选的后端连接状态，不做也可以。
- 移动端：顶部栏高度控制在 56px 内。

### 首页 Home.vue

必须保留的行为：

- 表单字段最终仍组装为 `TripFormData`。
- 日期格式仍为 `YYYY-MM-DD`。
- 时间格式仍为 `HH:mm`。
- 提交流程继续优先调用 `generateTripPlanStream`。
- SSE progress 事件继续更新进度条和状态文案。
- 成功后仍写入：
  - `sessionStorage.tripPlan`
  - `sessionStorage.tripPlanId`
  - `sessionStorage.agentDiagnostics`
- 成功后跳转 `/result?planId=...`。

体验改造建议：

- 将偏好选择改为更清晰的 segmented/chip 形式，选中态明确。
- 预算区增加前端校验：如果填写 `budget_per_day`，应满足 `budget_per_day * travel_days <= max_budget`。
- `max_budget` 后端要求如果填写必须大于 0，且小于 500 会报错；前端建议最小值设为 500，或者不填。
- 生成中禁止重复提交，保留可见进度。
- 加载态文案直接使用 SSE message，不要虚构进度。
- 日期结束时间早于开始时间时直接清空并提示。

### 结果页 Result.vue

必须保留的行为：

- 首先从 URL query 取 `planId`，有 `planId` 时调用 `getTripPlan(planId)`。
- 无 planId 或请求失败时，允许回退读取 sessionStorage 缓存。
- 编辑模式下可删除景点、移动景点顺序。
- 保存时调用 `updateTripPlan(planId, tripPlan, note)`，发送完整 `TripPlan`。
- 保存成功后更新本地缓存，并以服务端返回数据为准。
- 导出图片/PDF 时需要处理地图 canvas 快照。
- 地图继续使用 `VITE_AMAP_WEB_JS_KEY` 和 `@amap/amap-jsapi-loader`。

体验改造建议：

- 结果页首屏先给概要：城市、日期、总预算、总费用、风险数、天气摘要。
- 每日行程优先使用 timeline 展示；没有 timeline 时降级展示 attractions/meals。
- 地图不要在移动端首屏占满高度，建议放在 tab 或折叠段中。
- Agent 诊断属于开发/透明度信息，应默认折叠或放到底部。
- 风险提醒和 warnings 需要醒目，但不要使用大面积红色；按 `critical / warning / info` 分级。
- 编辑模式应在页面顶部显示轻量提示：“编辑后保存会触发后端重排时间线”。
- 对景点图片使用 `item.image_url` 或 `/api/poi/photo` 返回结果；失败时使用可辨识占位图，不要出现破图。

## 5. 后端契约

### 生成请求 TripFormData / TripRequest

前端提交字段必须与后端一致：

```ts
interface TripFormData {
  city: string
  start_date: string
  end_date: string
  travel_days: number
  transportation: string
  accommodation: string
  preferences: string[]
  free_text_input: string
  max_budget?: number
  budget_per_day?: number
  daily_start_time?: string
  daily_end_time?: string
  max_attractions_per_day?: number
}
```

后端还支持但当前前端未使用的字段：

- `budget_breakdown?: Record<string, number>`
- `max_walking_time?: number`
- `min_rest_time?: number`
- `avoid_rush_hour?: boolean`

除非要做明确需求，不建议这次加入 UI，避免扩大范围。

### SSE 响应

`POST /api/trip/plan/stream` 返回 `text/event-stream`：

```text
event: progress
data: {"step":"planning","percent":45,"message":"正在生成旅行计划"}

event: done
data: TripPlanResponse

event: error
data: {"message":"生成旅行计划失败: ..."}
```

前端只需要消费：

- `progress.data.percent`
- `progress.data.message`
- `done.data` 作为最终 `TripPlanResponse`
- `error.data.message` 作为错误提示

### TripPlanResponse

```ts
interface TripPlanResponse {
  success: boolean
  message: string
  plan_id?: string
  data?: TripPlan
  agent_diagnostics?: AgentDiagnostics
}
```

失败时后端也可能通过 HTTP 500 + `{ detail: string }` 返回，前端错误提示应优先读 `detail`。

### TripPlan

```ts
interface TripPlan {
  city: string
  start_date: string
  end_date: string
  days: DayPlan[]
  weather_info: WeatherInfo[]
  overall_suggestions: string
  budget?: Budget
  budget_usage?: BudgetUsage
  time_conflicts?: Conflict[]
  warnings?: string[]
}
```

字段渲染规则：

- `budget`、`budget_usage`、`time_conflicts`、`warnings` 都是可选字段，必须判空。
- `days` 是主内容，不能为空时展示每日行程；为空时展示空状态。
- `weather_info` 可能为空。
- `agent_diagnostics` 不属于 `TripPlan` 顶层展示主线，可单独存储和展示。

### DayPlan

```ts
interface DayPlan {
  date: string
  day_index: number
  description: string
  transportation: string
  accommodation: string
  hotel?: Hotel
  attractions: Attraction[]
  meals: Meal[]
  total_cost?: number
  total_duration?: number
  timeline?: TimelineItem[]
}
```

渲染优先级：

1. `timeline`：适合展示完整时间线。
2. `attractions`：适合卡片、地图 marker、编辑排序。
3. `meals`：适合嵌入当日行程或单独餐饮区。
4. `hotel`：适合当日底部推荐卡。

### Attraction

```ts
interface Attraction {
  name: string
  address: string
  location: { longitude: number; latitude: number }
  visit_duration: number
  description: string
  category?: string
  rating?: number
  image_url?: string
  ticket_price?: number
  opening_hours?: string
  visit_start_time?: string
  visit_end_time?: string
}
```

地图 marker 只在 `location.longitude` 和 `location.latitude` 都存在时渲染。

## 6. 组件拆分建议

如果只是美化，可继续保留 `Home.vue` 和 `Result.vue` 两个页面文件。若需要降低维护成本，建议只拆这些组件，不新增复杂状态管理：

```text
frontend/src/components/trip/
  TripRequestForm.vue       首页表单
  GenerationProgress.vue    SSE 生成进度
  TripSummaryBar.vue        结果页顶部摘要
  DayTimeline.vue           每日时间线
  AttractionCard.vue        景点卡片
  BudgetPanel.vue           预算明细
  RiskPanel.vue             warnings/time_conflicts
  TripMap.vue               AMap 初始化与 marker
  AgentDiagnosticsPanel.vue Agent 诊断折叠区
```

不要引入 Pinia、Redux、复杂图表库或新的后端 BFF。当前状态量可以由页面组件和 props 支撑。

## 7. 样式规范

建议使用 CSS 变量统一视觉：

```css
:root {
  --color-bg: #f6f8fb;
  --color-surface: #ffffff;
  --color-primary: #0f7b8a;
  --color-primary-soft: #e4f4f6;
  --color-accent: #f6b73c;
  --color-danger: #d64545;
  --color-warning: #b7791f;
  --color-text: #17202a;
  --color-muted: #6b7280;
  --radius-card: 8px;
  --shadow-card: 0 8px 24px rgba(15, 35, 52, 0.08);
}
```

约束：

- 卡片圆角不超过 8px，除非 Ant Design 组件天然样式需要。
- 不要继续使用满屏紫色渐变和浮动圆球背景。
- 字体不随视口宽度缩放。
- 重要数字使用等宽或 tabular number 样式。
- 中文按钮文案控制在 2 到 6 个字，例如“生成计划”“保存修改”“导出 PDF”。
- 图标可继续使用 emoji，但更推荐统一用 Ant Design Icons；如果新增图标库，需要先确认依赖策略。
- 所有按钮、标签、卡片在 360px 宽度下不能文字溢出。

## 8. 状态与异常

必须覆盖这些状态：

- 初始空表单。
- 表单校验失败。
- 生成中：SSE progress。
- 生成失败：HTTP 错误或 SSE error。
- 生成成功：跳转结果页。
- 结果页无缓存且无 planId：展示空状态和返回首页按钮。
- 获取 planId 失败：提示失败，可降级展示 sessionStorage。
- 地图加载失败：只隐藏地图功能，不影响行程阅读。
- 图片加载失败：显示占位图。
- 编辑未保存：取消时恢复 `originalPlan`。
- 保存失败：保留编辑内容，不静默丢失。

错误提示要具体，例如“保存失败：旅行计划不存在”，不要只写“出错了”。

## 9. 响应式要求

断点建议：

- `>= 1200px`：左侧导航 + 主内容 + 地图并列。
- `768px - 1199px`：顶部摘要 + 内容单列，地图可放到摘要下方。
- `< 768px`：不使用固定侧边导航，改为顶部横向 tab 或锚点 chips。

移动端重点：

- 首页表单单列展示。
- 日期选择、时间选择和数字输入宽度 100%。
- 结果页操作按钮可折行，但不能遮挡标题。
- 地图高度建议 260px 到 340px。
- 每日行程优先展示时间、地点、费用，不要让长描述撑爆卡片。

## 10. 验收清单

前端工程师提交前请完成：

- `npm run build` 通过。
- 首页能成功调用 `/api/trip/plan/stream` 并展示进度。
- 成功生成后能进入 `/result?planId=...`。
- 刷新结果页后能通过 `planId` 重新获取数据。
- 无 `planId` 时仍可从 sessionStorage 回退展示。
- 编辑删除/移动景点后能保存，保存后页面使用后端返回的新计划。
- 地图 marker 和路线在有经纬度时正常显示。
- 景点图片接口失败时不破图。
- 图片导出和 PDF 导出可用。
- 360px、768px、1440px 三个宽度下没有文本重叠或按钮溢出。
- 浏览器控制台无未处理异常。

## 11. 建议实施顺序

1. 修复 `App.vue` 全局乱码和外壳布局。
2. 整理首页表单结构与响应式布局，保留提交逻辑。
3. 重做结果页信息架构：顶部摘要、每日行程、地图、预算、风险。
4. 将 Agent 诊断默认折叠。
5. 处理移动端和导出样式。
6. 最后做视觉润色、空状态和错误状态。

本次设计改造不建议修改后端，也不建议扩展新的业务字段。若确实需要新增字段，应先同步修改 `backend/app/models/schemas.py`、`frontend/src/types/index.ts` 和接口调用逻辑。
