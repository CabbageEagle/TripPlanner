"""可视化 LangGraph 工作流图"""

from app.agents.trip_planner_agent_langgraph import get_trip_planner_agent

def visualize_graph():
    """生成工作流图的 Mermaid 图表"""
    planner = get_trip_planner_agent()
    
    # 生成 Mermaid 图表代码
    print("\n" + "="*60)
    print("LangGraph 工作流图 (Mermaid格式)")
    print("="*60 + "\n")
    
    mermaid_code = """```mermaid
graph TD
    Start([开始]) --> A[搜索景点]
    A --> B[查询天气]
    B --> C[搜索酒店]
    C --> D[生成计划]
    D --> E[解析计划]
    
    E -->|解析成功| F{校验计划}
    E -->|解析失败| Error[错误处理]
    
    F -->|无问题| End([结束])
    F -->|有问题| G{检查重试次数}
    
    G -->|未达上限| H[修复计划]
    G -->|达到上限| End
    
    H --> E
    Error --> End
    
    style Start fill:#90EE90
    style End fill:#FFB6C1
    style F fill:#FFD700
    style G fill:#FFD700
    style Error fill:#FF6B6B
```"""
    
    print(mermaid_code)
    print("\n" + "="*60)
    print("工作流说明:")
    print("="*60)
    print("""
1. 数据收集阶段:
   - 搜索景点 → 查询天气 → 搜索酒店

2. 规划生成阶段:
   - 生成计划 (LLM 输出原始文本)

3. 验证回环阶段:
   - 解析计划 (提取结构化 JSON)
   - 校验计划 (检查完整性和合理性)
   - 修复计划 (针对问题进行修复)
   - 重新解析 (回到解析环节)

4. 控制流特性:
   - 解析最多重试 3 次
   - 验证最多重试 3 次
   - 轻微问题直接通过
   - 严重问题触发修复
   - 达到重试上限强制结束
""")

if __name__ == "__main__":
    visualize_graph()
