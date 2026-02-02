# 验证-修复循环优化策略

## 🎯 核心优化原则

### 1. 快速失败 (Fast Fail)
- 严重问题立即终止，不浪费时间修复
- 只修复"可修复"的问题

### 2. 渐进式修复 (Progressive Fix)
- 按问题优先级修复
- 每次只修复最关键的 1-2 个问题

### 3. 智能退出 (Smart Exit)
- 设置合理的重试上限
- 检测修复是否有效
- 发现无效修复立即停止

### 4. 问题分类 (Issue Classification)
- **Critical（必须修复）**: 缺少关键字段、数据为空
- **High（应该修复）**: 天数不匹配、景点过少
- **Medium（可以修复）**: 餐食不完整、时间冲突
- **Low（接受）**: 格式问题、非关键字段缺失

## 🔧 优化实现

### 1. 修改验证逻辑 - 问题分级

```python
def verify_plan_node(state: TripPlannerState) -> Dict[str, Any]:
    """校验节点：检查计划的完整性和合理性"""
    violations = []
    
    # 关键问题（必须修复）
    if not final_plan:
        violations.append({
            "type": "missing_plan",
            "severity": "critical",
            "fixable": False,  # 无法修复，应该重新生成
            "message": "计划数据为空"
        })
    
    # 可修复问题
    if len(days) != request.travel_days:
        violations.append({
            "type": "days_mismatch",
            "severity": "critical",
            "fixable": True,  # 可以修复
            "message": f"天数不匹配",
            "expected": request.travel_days,
            "actual": len(days)
        })
    
    # 轻微问题（可接受）
    if len(attractions) < 2:
        violations.append({
            "type": "insufficient_attractions",
            "severity": "medium",
            "fixable": True,
            "message": "景点数量不足"
        })
```

### 2. 智能路由决策

```python
def should_fix_or_end(state: TripPlannerState) -> Literal["fix_plan", "END"]:
    violations = state.get("violations", [])
    verify_count = state.get("verify_count", 0)
    
    # 策略1: 无问题直接结束
    if not violations:
        return "END"
    
    # 策略2: 检查是否有不可修复的问题
    unfixable = [v for v in violations if not v.get("fixable", True)]
    if unfixable:
        print(f"⚠️  发现不可修复问题，放弃修复")
        return "END"
    
    # 策略3: 限制修复次数（1次）
    if verify_count >= 1:
        print(f"⚠️  已尝试修复，接受当前结果")
        return "END"
    
    # 策略4: 只修复 critical 且 fixable 的问题
    fixable_critical = [
        v for v in violations 
        if v.get("severity") == "critical" and v.get("fixable", True)
    ]
    
    if fixable_critical and len(fixable_critical) <= 3:
        print(f"🔧 修复 {len(fixable_critical)} 个关键问题")
        return "fix_plan"
    
    # 策略5: 其他情况接受
    return "END"
```

### 3. 针对性修复

```python
def fix_plan_node(state: TripPlannerState) -> Dict[str, Any]:
    violations = state.get("violations", [])
    
    # 只提取可修复的 critical 问题
    fixable_issues = [
        v for v in violations 
        if v.get("severity") == "critical" and v.get("fixable", True)
    ]
    
    # 如果没有可修复问题，直接返回
    if not fixable_issues:
        return {
            "final_plan_raw": json.dumps(final_plan, ensure_ascii=False),
            "current_step": "plan_fixed"
        }
    
    # 构建精准的修复指令
    issues_text = "\n".join([
        f"{i+1}. {v['message']}" + 
        (f" (期望: {v.get('expected')}, 实际: {v.get('actual')})" if 'expected' in v else "")
        for i, v in enumerate(fixable_issues)
    ])
    
    system_prompt = f"""你是行程修复专家。请针对以下 {len(fixable_issues)} 个问题进行精准修复：

{issues_text}

修复规则：
1. 只修复列出的问题
2. 保持其他部分不变
3. 确保修复后的计划完整有效
4. 返回完整 JSON（不要省略）

当前计划有 {len(final_plan.get('days', []))} 天，需要修改为 {request.travel_days} 天。
"""
    
    # 缩短输入，只传递关键信息
    compact_plan = {
        "city": final_plan.get("city"),
        "start_date": final_plan.get("start_date"),
        "end_date": final_plan.get("end_date"),
        "days": final_plan.get("days", [])[:2]  # 只传前2天作为示例
    }
    
    user_query = f"当前计划:\n{json.dumps(compact_plan, ensure_ascii=False, indent=2)}"
```

### 4. 修复效果检测

```python
def verify_plan_node(state: TripPlannerState) -> Dict[str, Any]:
    verify_count = state.get("verify_count", 0)
    previous_violations = state.get("previous_violations", [])
    
    # ... 验证逻辑 ...
    
    # 检测修复是否有效
    if verify_count > 0:
        if len(violations) >= len(previous_violations):
            print("⚠️  修复无效或引入新问题，停止修复")
            # 强制结束，不再修复
            return {
                "violations": None,  # 清空违规，强制结束
                "verify_count": verify_count + 1,
                "current_step": "verify_passed"
            }
    
    return {
        "violations": violations if violations else None,
        "previous_violations": violations,  # 记录本次违规
        "verify_count": verify_count + 1,
        "current_step": "verify_passed" if not violations else "verify_failed"
    }
```

### 5. 状态更新优化

```python
# 在 graph_state.py 中添加
class TripPlannerState(TypedDict):
    # ... 现有字段 ...
    previous_violations: Optional[list[Dict[str, Any]]]  # 上次验证的问题
    fix_attempted: bool  # 是否已尝试修复
```

## 📊 优化效果预期

### 时间对比

**优化前（最坏情况）：**
```
数据收集: 30s
生成: 30s
解析: 1s
验证: 1s
修复: 30s → 解析: 1s → 验证: 1s (发现问题)
修复: 30s → 解析: 1s → 验证: 1s (还有问题)
修复: 30s → 解析: 1s → 验证: 1s
总计: 约 150s (2.5分钟)
```

**优化后（正常情况）：**
```
数据收集: 30s
生成: 30s
解析: 1s
验证: 1s (发现可修复问题)
修复: 30s → 解析: 1s → 验证: 1s (修复成功)
总计: 约 94s (1.5分钟)
```

**优化后（快速路径）：**
```
数据收集: 30s
生成: 30s
解析: 1s
验证: 1s (无问题或轻微问题)
总计: 约 62s (1分钟)
```

## 🎯 推荐配置

```python
# config.py
class Settings(BaseSettings):
    # 验证配置
    max_verify_attempts: int = 1  # 只验证1次
    max_fix_attempts: int = 1     # 最多修复1次
    
    # 问题阈值
    max_fixable_issues: int = 3   # 超过3个问题不修复
    
    # 严重程度配置
    fix_critical_only: bool = True  # 只修复 critical 问题
    
    # 超时配置
    llm_timeout: int = 60  # LLM 调用超时 60秒
```

## ✅ 实施建议

1. **第一阶段：添加问题分级**
   - 为每个 violation 添加 `fixable` 标记
   - 区分 critical/high/medium/low

2. **第二阶段：优化路由逻辑**
   - 实现智能决策
   - 添加修复效果检测

3. **第三阶段：精简修复**
   - 只传必要信息给 LLM
   - 使用更精确的修复提示词

4. **第四阶段：监控优化**
   - 记录修复成功率
   - 统计平均耗时
   - 持续调整阈值
