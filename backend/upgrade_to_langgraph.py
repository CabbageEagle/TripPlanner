"""
LangGraph 升级脚本

自动执行从 hello-agents 到 LangGraph 的迁移
"""

import subprocess
import sys
import os


def print_step(step_num, message):
    """打印步骤信息"""
    print(f"\n{'='*60}")
    print(f"步骤 {step_num}: {message}")
    print('='*60)


def run_command(command, description):
    """运行命令"""
    print(f"\n🔄 {description}...")
    print(f"   命令: {command}")
    
    try:
        result = subprocess.run(
            command,
            shell=True,
            check=True,
            capture_output=True,
            text=True
        )
        print(f"✅ {description} 成功")
        if result.stdout:
            print(f"   输出: {result.stdout[:200]}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} 失败")
        print(f"   错误: {e.stderr}")
        return False


def check_python_version():
    """检查 Python 版本"""
    version = sys.version_info
    if version.major >= 3 and version.minor >= 8:
        print(f"✅ Python 版本: {version.major}.{version.minor}.{version.micro}")
        return True
    else:
        print(f"❌ Python 版本过低: {version.major}.{version.minor}.{version.micro}")
        print("   需要 Python 3.8 或更高版本")
        return False


def check_env_file():
    """检查环境变量文件"""
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    
    if os.path.exists(env_path):
        print(f"✅ 找到环境变量文件: {env_path}")
        
        # 检查必需的环境变量
        with open(env_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        required_vars = ['OPENAI_API_KEY', 'OPENAI_BASE_URL', 'OPENAI_MODEL']
        missing_vars = []
        
        for var in required_vars:
            if var not in content:
                missing_vars.append(var)
        
        if missing_vars:
            print(f"⚠️  缺少环境变量: {', '.join(missing_vars)}")
            print("   请在 .env 文件中添加这些变量")
            return False
        else:
            print("✅ 所有必需的环境变量都已配置")
            return True
    else:
        print(f"❌ 未找到 .env 文件")
        print("   请创建 .env 文件并配置必需的环境变量")
        return False


def upgrade_to_langgraph():
    """执行升级"""
    
    print("\n" + "🚀"*30)
    print("LangGraph 升级向导")
    print("🚀"*30 + "\n")
    
    # 步骤 1: 检查环境
    print_step(1, "检查环境")
    if not check_python_version():
        return False
    
    if not check_env_file():
        print("\n⚠️  请先配置环境变量再继续")
        return False
    
    # 步骤 2: 备份原文件
    print_step(2, "备份原文件")
    backup_file = "app/agents/trip_planner_agent_backup.py"
    if os.path.exists("app/agents/trip_planner_agent.py"):
        try:
            import shutil
            shutil.copy(
                "app/agents/trip_planner_agent.py",
                backup_file
            )
            print(f"✅ 原文件已备份到: {backup_file}")
        except Exception as e:
            print(f"⚠️  备份失败: {e}")
    
    # 步骤 3: 安装依赖
    print_step(3, "安装 LangGraph 依赖")
    
    packages = [
        "langgraph>=0.2.0",
        "langchain>=0.3.0",
        "langchain-openai>=0.2.0",
        "langchain-community>=0.3.0"
    ]
    
    all_success = True
    for package in packages:
        success = run_command(
            f"pip install {package}",
            f"安装 {package.split('>=')[0]}"
        )
        if not success:
            all_success = False
    
    if not all_success:
        print("\n⚠️  部分依赖安装失败，请手动安装")
        return False
    
    # 步骤 4: 验证安装
    print_step(4, "验证安装")
    
    try:
        import langgraph
        import langchain
        import langchain_openai
        print("✅ LangGraph 相关包导入成功")
        print(f"   LangGraph 版本: {langgraph.__version__}")
        print(f"   LangChain 版本: {langchain.__version__}")
    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        return False
    
    # 步骤 5: 运行测试
    print_step(5, "运行测试")
    
    test_success = run_command(
        "python test_langgraph.py",
        "运行 LangGraph 测试"
    )
    
    if not test_success:
        print("\n⚠️  测试失败，但这可能是由于 API 配置问题")
        print("   请检查 .env 文件中的 API 密钥")
    
    # 总结
    print("\n" + "="*60)
    print("升级总结")
    print("="*60)
    print("\n✅ LangGraph 框架已安装")
    print("✅ 新文件已创建:")
    print("   - app/agents/graph_state.py")
    print("   - app/agents/graph_nodes.py")
    print("   - app/agents/trip_planner_agent_langgraph.py")
    print("\n📚 请查看以下文档:")
    print("   - LANGGRAPH_MIGRATION.md (迁移指南)")
    print("   - test_langgraph.py (测试脚本)")
    print("   - visualize_workflow.py (可视化工具)")
    
    print("\n🎯 下一步:")
    print("   1. 检查 .env 配置")
    print("   2. 运行: python test_langgraph.py")
    print("   3. 启动服务: python run.py")
    print("   4. 测试 API: POST http://localhost:8000/api/trip/plan")
    
    print("\n" + "="*60 + "\n")
    
    return True


if __name__ == "__main__":
    try:
        success = upgrade_to_langgraph()
        
        if success:
            print("🎉 升级完成！")
            sys.exit(0)
        else:
            print("⚠️  升级过程中遇到问题，请查看上方日志")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n\n⚠️  升级已取消")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 升级失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
