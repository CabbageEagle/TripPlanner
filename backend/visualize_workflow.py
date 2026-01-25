"""
LangGraph 工作流可视化脚本

运行此脚本可以生成工作流的可视化图表
需要安装: pip install graphviz
"""

from app.agents.trip_planner_agent_langgraph import LangGraphTripPlanner


def visualize_workflow():
    """生成并保存工作流可视化图"""
    try:
        # 创建规划器实例
        planner = LangGraphTripPlanner()
        
        # 生成图的 Mermaid 格式（文本）
        print("\n" + "="*60)
        print("LangGraph 工作流结构")
        print("="*60)
        print("\n工作流节点:")
        print("1. search_attractions (搜索景点)")
        print("2. query_weather (查询天气)")
        print("3. search_hotels (搜索酒店)")
        print("4. plan_trip (生成计划)")
        print("5. error_handler (错误处理)")
        
        print("\n工作流路径:")
        print("START")
        print("  └─> search_attractions")
        print("       └─> query_weather")
        print("            └─> search_hotels")
        print("                 └─> plan_trip")
        print("                      └─> END")
        
        print("\n" + "="*60)
        
        # 尝试生成可视化图（需要 graphviz）
        try:
            from IPython.display import Image, display
            
            # 获取图的可视化
            img = planner.app.get_graph().draw_mermaid_png()
            
            # 保存图片
            with open("langgraph_workflow.png", "wb") as f:
                f.write(img)
            
            print("✅ 工作流图已保存为: langgraph_workflow.png")
            
        except ImportError:
            print("⚠️  未安装 graphviz，跳过图片生成")
            print("   安装命令: pip install graphviz")
        except Exception as e:
            print(f"⚠️  图片生成失败: {e}")
        
        # 生成 Mermaid 代码
        print("\nMermaid 图表代码 (可在 https://mermaid.live 查看):")
        print("-"*60)
        mermaid_code = """
graph TB
    START([开始]) --> A[搜索景点<br/>search_attractions]
    A --> B[查询天气<br/>query_weather]
    B --> C[搜索酒店<br/>search_hotels]
    C --> D[生成计划<br/>plan_trip]
    D --> END([结束])
    
    style START fill:#90EE90
    style END fill:#FFB6C1
    style A fill:#87CEEB
    style B fill:#DDA0DD
    style C fill:#F0E68C
    style D fill:#FFA07A
"""
        print(mermaid_code)
        print("-"*60)
        
        # 保存 Mermaid 代码
        with open("langgraph_workflow.mmd", "w", encoding="utf-8") as f:
            f.write(mermaid_code)
        print("✅ Mermaid 代码已保存为: langgraph_workflow.mmd")
        
    except Exception as e:
        print(f"❌ 可视化失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    visualize_workflow()
