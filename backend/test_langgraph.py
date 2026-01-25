"""
LangGraph 框架测试脚本

测试新的 LangGraph 实现是否正常工作
"""

import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agents.trip_planner_agent_langgraph import get_trip_planner_agent
from app.models.schemas import TripRequest


def test_langgraph_planner():
    """测试 LangGraph 旅行规划器"""
    
    print("\n" + "="*60)
    print("LangGraph 旅行规划器测试")
    print("="*60 + "\n")
    
    try:
        # 1. 初始化测试
        print("步骤 1: 初始化 LangGraph 规划器...")
        planner = get_trip_planner_agent()
        print("✅ 初始化成功\n")
        
        # 2. 创建测试请求
        print("步骤 2: 创建测试请求...")
        test_request = TripRequest(
            city="北京",
            start_date="2024-06-01",
            end_date="2024-06-03",
            travel_days=3,
            preferences=["历史文化", "美食"],
            transportation="公共交通",
            accommodation="经济型酒店",
            free_text_input="希望能参观故宫和长城"
        )
        print(f"✅ 测试请求创建成功")
        print(f"   城市: {test_request.city}")
        print(f"   天数: {test_request.travel_days}")
        print(f"   偏好: {', '.join(test_request.preferences)}\n")
        
        # 3. 运行工作流
        print("步骤 3: 运行 LangGraph 工作流...")
        print("-"*60)
        
        trip_plan = planner.plan_trip(test_request)
        
        print("-"*60)
        print("✅ 工作流执行成功\n")
        
        # 4. 验证结果
        print("步骤 4: 验证结果...")
        assert trip_plan.city == test_request.city, "城市不匹配"
        assert len(trip_plan.days) == test_request.travel_days, "天数不匹配"
        print(f"✅ 结果验证通过")
        print(f"   城市: {trip_plan.city}")
        print(f"   天数: {len(trip_plan.days)}")
        print(f"   总建议: {trip_plan.overall_suggestions[:100]}...\n")
        
        # 5. 显示详细信息
        print("步骤 5: 显示计划详情...")
        print("-"*60)
        for i, day in enumerate(trip_plan.days):
            print(f"\n第 {i+1} 天 ({day.date}):")
            print(f"  描述: {day.description}")
            print(f"  景点数: {len(day.attractions)}")
            print(f"  餐饮数: {len(day.meals)}")
            if day.hotel:
                print(f"  酒店: {day.hotel.name}")
        
        if trip_plan.weather_info:
            print(f"\n天气信息: {len(trip_plan.weather_info)} 天")
        
        if trip_plan.budget:
            print(f"\n预算信息:")
            print(f"  总费用: ¥{trip_plan.budget.total}")
        
        print("-"*60)
        
        print("\n" + "="*60)
        print("✅ 所有测试通过!")
        print("="*60 + "\n")
        
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_error_handling():
    """测试错误处理"""
    print("\n" + "="*60)
    print("错误处理测试")
    print("="*60 + "\n")
    
    try:
        planner = get_trip_planner_agent()
        
        # 创建一个可能导致问题的请求
        problematic_request = TripRequest(
            city="",  # 空城市名
            start_date="2024-06-01",
            end_date="2024-06-03",
            travel_days=3,
            preferences=[],
            transportation="公共交通",
            accommodation="经济型酒店"
        )
        
        print("测试空城市名的处理...")
        trip_plan = planner.plan_trip(problematic_request)
        
        if trip_plan:
            print("✅ 错误处理正常，返回了备用计划")
            return True
        else:
            print("⚠️  未返回计划")
            return False
            
    except Exception as e:
        print(f"⚠️  捕获到异常（预期行为）: {str(e)}")
        return True


if __name__ == "__main__":
    print("\n🚀 开始 LangGraph 测试套件\n")
    
    # 测试 1: 正常流程
    success1 = test_langgraph_planner()
    
    # 测试 2: 错误处理
    success2 = test_error_handling()
    
    # 总结
    print("\n" + "="*60)
    print("测试总结")
    print("="*60)
    print(f"正常流程测试: {'✅ 通过' if success1 else '❌ 失败'}")
    print(f"错误处理测试: {'✅ 通过' if success2 else '❌ 失败'}")
    print("="*60 + "\n")
    
    if success1 and success2:
        print("🎉 所有测试通过！LangGraph 集成成功！\n")
        sys.exit(0)
    else:
        print("⚠️  部分测试失败，请检查日志\n")
        sys.exit(1)
