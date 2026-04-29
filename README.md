# HelloAgents Trip Planner

智能旅行规划系统。当前主链路基于 LangGraph 编排，结合高德地图服务、LLM、RAG 记忆、规则排程和校验修复闭环，生成可展示、可编辑、可保存的多日行程。

## 核心能力

- LangGraph 工作流：信息收集、行程生成、JSON 解析、自动排程、规则校验、失败修复。
- 四 Agent 职责收敛：信息收集决策 agent、行程生成 agent、计划修复 agent、可选质量评估 agent。
- 工具能力封装：天气、景点、酒店、本地活动、交通时间均通过 `@tool + Pydantic` 封装并注册到 `CAPABILITY_TOOLS`。
- 信息收集 SOP：景点和天气为基础必查项，酒店和交通按请求与候选风险触发，本地活动只作为可选惊喜增强项。
- RAG 记忆增强：从历史偏好和用户编辑中提炼记忆，规划时召回并注入上下文。
- 编辑闭环：前端编辑后保存版本，后端自动重排并沉淀新的偏好信号。

## 技术栈

### 后端

- FastAPI
- LangGraph / LangChain
- OpenAI-compatible LLM API
- SQLAlchemy + PostgreSQL + pgvector
- 高德地图服务封装

### 前端

- Vue 3
- TypeScript
- Vite
- Ant Design Vue
- 高德地图 JavaScript API

## 项目结构

```text
helloagents-trip-planner/
├── backend/
│   ├── app/
│   │   ├── agents/
│   │   │   ├── graph_state.py
│   │   │   ├── graph_nodes.py
│   │   │   ├── trip_planner_agent_langgraph.py
│   │   │   └── tools/
│   │   │       ├── __init__.py
│   │   │       ├── attractions_tool.py
│   │   │       ├── weather_tool.py
│   │   │       ├── hotels_tool.py
│   │   │       ├── local_events_tool.py
│   │   │       └── transit_tool.py
│   │   ├── api/
│   │   ├── db/
│   │   ├── models/
│   │   ├── repositories/
│   │   ├── services/
│   │   └── config.py
│   └── test_*.py
├── frontend/
│   └── src/
├── docs/
├── PROJECT_INTRODUCTION.md
└── README.md
```

## LangGraph 主流程

```mermaid
flowchart TD
    A["init_info_gathering"] --> B["info_gathering_agent"]
    B -->|"call_tool"| C["tool executor nodes"]
    C --> D["merge_tool_result"]
    D --> B
    B -->|"submit_context"| E["plan_trip"]
    B -->|"forced exit"| E
    E --> F["parse_plan"]
    F -->|"parsed"| G["schedule_plan"]
    F -->|"retry parse"| F
    F -->|"exhausted"| K["error_handler"]
    G --> H["verify_plan"]
    H -->|"needs fix"| I["fix_plan"]
    I --> G
    H -->|"passed"| J["END"]
    K --> J
```

信息收集阶段的工具执行节点不是小 agent，只负责从 state 组装输入、调用 registry 中的 tool、把结果写回 `gathered_context` 和 `tool_call_history`。下一步调用哪个工具由 `info_gathering_agent_node` 决策，默认可使用规则兜底，也可通过 `INFO_GATHERING_USE_LLM` 开启 LLM 决策。

## 工具注册

统一入口位于 `backend/app/agents/tools/__init__.py`：

```python
CAPABILITY_TOOLS = {
    "estimate_transit_time_tool": estimate_transit_time_tool,
    "query_weather_tool": query_weather_tool,
    "search_attractions_tool": search_attractions_tool,
    "search_hotels_tool": search_hotels_tool,
    "search_local_events_tool": search_local_events_tool,
}
```

新增工具的推荐流程：

1. 在 `backend/app/agents/tools/` 新增 tool 文件。
2. 用 Pydantic `BaseModel` 定义输入 schema。
3. 用 `@tool(args_schema=...)` 封装能力，并在 docstring 写清何时使用、输入约束、输出语义。
4. Tool 只调用 service，不直接读写 graph state。
5. 在 `CAPABILITY_TOOLS` 注册。
6. 在 `graph_nodes.py` 增加薄 adapter：构造输入、调用 registry、写回 state。
7. 在 planner prompt 中说明如何消费该上下文。
8. 补充 tool、adapter、planner 消费规则的测试。

## 配置

后端环境变量主要包括：

```env
LLM_API_KEY=your_llm_api_key
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL=qwen3.5-plus
LLM_EMBEDDING_MODEL=text-embedding-3-small
JUDGE_MODEL=glm-4.7
INFO_GATHERING_USE_LLM=true
AMAP_API_KEY=your_amap_key
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/trip_planner
RAG_DEBUG=false
```

`INFO_GATHERING_USE_LLM=true` 时，信息收集决策 agent 会请求 LLM 输出严格 JSON；解析失败、非法工具、跳过必查 SOP、提前提交等情况会回退到规则决策。

## 快速启动

### 后端

```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

也可以直接运行：

```bash
uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8000
```

API 文档地址：`http://localhost:8000/docs`

### 前端

```bash
cd frontend
npm install
npm run dev
```

默认访问：`http://localhost:5173`

## 测试

当前关键回归命令：

```bash
python backend/test_phase1_info_gathering.py
python backend/test_local_events_tooling.py
python backend/test_phase3_transit_filtering.py
python -m unittest discover backend -p "test_*.py"
```

`backend/test_langgraph.py` 更接近手工端到端脚本，可能触发真实 LLM/API 链路，不建议作为快速单元回归条件。

## 关键文档

- `PROJECT_INTRODUCTION.md`：当前架构、pipeline、RAG、状态与能力封装说明。

