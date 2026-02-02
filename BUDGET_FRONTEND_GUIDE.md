# 预算询问功能 - 前端实现指南

## 📋 改进说明

### 后端改动（已完成）

1. **预算必填**
   - `max_budget` 从可选改为必填
   - 添加了 `gt=0` 验证（必须大于0）
   - 添加了最小值检查（至少500元）

2. **预算验证**
   - 总预算必须 > 0
   - 总预算建议 >= 500元
   - 每日预算 × 天数 不能超过总预算

3. **更好的提示文案**
   - 必填项明确标注
   - 可选项说明"不填则自动分配"

## 🎨 前端实现建议

### 1. 表单字段优化

```vue
<!-- Home.vue 或相关表单组件 -->
<template>
  <div class="budget-section">
    <h3>💰 预算设置</h3>
    
    <!-- 总预算 - 必填 -->
    <div class="form-item required">
      <label for="max-budget">
        总预算 <span class="required-mark">*</span>
        <span class="tip">（本次旅行的最高消费额度）</span>
      </label>
      <a-input-number
        id="max-budget"
        v-model:value="formData.max_budget"
        :min="500"
        :max="100000"
        :step="100"
        placeholder="请输入总预算"
        style="width: 100%"
      >
        <template #addonAfter>元</template>
      </a-input-number>
      <div class="budget-tips">
        <p>💡 建议预算参考：</p>
        <ul>
          <li>经济游：500-1000元/天</li>
          <li>舒适游：1000-2000元/天</li>
          <li>豪华游：2000元以上/天</li>
        </ul>
      </div>
    </div>

    <!-- 每日预算 - 可选 -->
    <div class="form-item">
      <label for="budget-per-day">
        每日预算
        <span class="optional-mark">（可选）</span>
        <span class="tip">（不填则根据总预算自动分配）</span>
      </label>
      <a-input-number
        id="budget-per-day"
        v-model:value="formData.budget_per_day"
        :min="100"
        :max="formData.max_budget"
        :step="50"
        placeholder="不填则自动分配"
        style="width: 100%"
      >
        <template #addonAfter>元/天</template>
      </a-input-number>
    </div>

    <!-- 预算分配 - 高级选项 -->
    <a-collapse v-model:activeKey="activeKey">
      <a-collapse-panel key="1" header="📊 详细预算分配（高级）">
        <div class="budget-breakdown">
          <div class="breakdown-item">
            <label>景点门票</label>
            <a-input-number
              v-model:value="formData.budget_breakdown.attractions"
              :min="0"
              :step="50"
              placeholder="自动"
            >
              <template #addonAfter>元</template>
            </a-input-number>
          </div>
          
          <div class="breakdown-item">
            <label>餐饮美食</label>
            <a-input-number
              v-model:value="formData.budget_breakdown.meals"
              :min="0"
              :step="50"
              placeholder="自动"
            >
              <template #addonAfter>元</template>
            </a-input-number>
          </div>
          
          <div class="breakdown-item">
            <label>住宿酒店</label>
            <a-input-number
              v-model:value="formData.budget_breakdown.hotels"
              :min="0"
              :step="50"
              placeholder="自动"
            >
              <template #addonAfter>元</template>
            </a-input-number>
          </div>
          
          <div class="breakdown-item">
            <label>交通出行</label>
            <a-input-number
              v-model:value="formData.budget_breakdown.transportation"
              :min="0"
              :step="50"
              placeholder="自动"
            >
              <template #addonAfter>元</template>
            </a-input-number>
          </div>
        </div>
      </a-collapse-panel>
    </a-collapse>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'

const formData = ref({
  max_budget: undefined as number | undefined,
  budget_per_day: undefined as number | undefined,
  travel_days: 3,
  budget_breakdown: {
    attractions: undefined,
    meals: undefined,
    hotels: undefined,
    transportation: undefined
  }
})

// 自动计算建议的每日预算
const suggestedDailyBudget = computed(() => {
  if (formData.value.max_budget && formData.value.travel_days) {
    return Math.floor(formData.value.max_budget / formData.value.travel_days)
  }
  return 0
})

// 监听总预算变化，提供建议
watch(() => formData.value.max_budget, (newBudget) => {
  if (newBudget && !formData.value.budget_per_day) {
    // 自动填充建议的每日预算
    formData.value.budget_per_day = suggestedDailyBudget.value
  }
})

// 表单验证
const validateBudget = () => {
  if (!formData.value.max_budget) {
    return { valid: false, message: '请输入总预算' }
  }
  
  if (formData.value.max_budget < 500) {
    return { valid: false, message: '预算过低，建议至少500元' }
  }
  
  if (formData.value.budget_per_day) {
    const totalDaily = formData.value.budget_per_day * formData.value.travel_days
    if (totalDaily > formData.value.max_budget) {
      return { 
        valid: false, 
        message: `每日预算(${formData.value.budget_per_day}元) × ${formData.value.travel_days}天 = ${totalDaily}元，超过总预算`
      }
    }
  }
  
  return { valid: true }
}
</script>

<style scoped>
.budget-section {
  padding: 20px;
  background: #f9f9f9;
  border-radius: 8px;
  margin: 20px 0;
}

.form-item {
  margin-bottom: 20px;
}

.required-mark {
  color: #ff4d4f;
  margin-left: 4px;
}

.optional-mark {
  color: #999;
  font-size: 12px;
}

.tip {
  color: #666;
  font-size: 12px;
  margin-left: 8px;
}

.budget-tips {
  margin-top: 8px;
  padding: 12px;
  background: #e6f7ff;
  border-left: 3px solid #1890ff;
  border-radius: 4px;
  font-size: 13px;
}

.budget-tips ul {
  margin: 8px 0 0 0;
  padding-left: 20px;
}

.budget-tips li {
  margin: 4px 0;
  color: #666;
}

.budget-breakdown {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}

.breakdown-item label {
  display: block;
  margin-bottom: 8px;
  font-weight: 500;
}
</style>
```

### 2. 智能预算建议

```typescript
// src/utils/budgetHelper.ts

export interface BudgetSuggestion {
  level: 'economy' | 'comfort' | 'luxury'
  label: string
  dailyRange: [number, number]
  breakdown: {
    attractions: number
    meals: number
    hotels: number
    transportation: number
  }
}

export const budgetSuggestions: BudgetSuggestion[] = [
  {
    level: 'economy',
    label: '经济游',
    dailyRange: [500, 1000],
    breakdown: {
      attractions: 100,
      meals: 150,
      hotels: 200,
      transportation: 50
    }
  },
  {
    level: 'comfort',
    label: '舒适游',
    dailyRange: [1000, 2000],
    breakdown: {
      attractions: 200,
      meals: 300,
      hotels: 400,
      transportation: 100
    }
  },
  {
    level: 'luxury',
    label: '豪华游',
    dailyRange: [2000, 5000],
    breakdown: {
      attractions: 400,
      meals: 600,
      hotels: 800,
      transportation: 200
    }
  }
]

export function calculateBudgetSuggestion(days: number, level: 'economy' | 'comfort' | 'luxury') {
  const suggestion = budgetSuggestions.find(s => s.level === level)
  if (!suggestion) return null
  
  const avgDaily = (suggestion.dailyRange[0] + suggestion.dailyRange[1]) / 2
  const total = avgDaily * days
  
  return {
    total,
    daily: avgDaily,
    breakdown: {
      attractions: suggestion.breakdown.attractions * days,
      meals: suggestion.breakdown.meals * days,
      hotels: suggestion.breakdown.hotels * days,
      transportation: suggestion.breakdown.transportation * days
    }
  }
}
```

### 3. 预算选择器组件

```vue
<!-- BudgetSelector.vue -->
<template>
  <div class="budget-selector">
    <h4>快速选择预算档次</h4>
    <div class="budget-cards">
      <div 
        v-for="suggestion in suggestions"
        :key="suggestion.level"
        class="budget-card"
        :class="{ active: selected === suggestion.level }"
        @click="selectBudget(suggestion)"
      >
        <div class="card-header">
          <span class="card-icon">{{ getIcon(suggestion.level) }}</span>
          <span class="card-title">{{ suggestion.label }}</span>
        </div>
        <div class="card-content">
          <div class="daily-range">
            {{ suggestion.dailyRange[0] }} - {{ suggestion.dailyRange[1] }} 元/天
          </div>
          <div class="total-budget" v-if="travelDays">
            总预算: {{ calculateTotal(suggestion, travelDays) }} 元
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { budgetSuggestions } from '@/utils/budgetHelper'

const props = defineProps<{
  travelDays: number
}>()

const emit = defineEmits<{
  select: [budget: number, level: string]
}>()

const selected = ref<string | null>(null)

const getIcon = (level: string) => {
  const icons = {
    economy: '💰',
    comfort: '🏖️',
    luxury: '👑'
  }
  return icons[level] || '💰'
}

const calculateTotal = (suggestion, days: number) => {
  const avg = (suggestion.dailyRange[0] + suggestion.dailyRange[1]) / 2
  return Math.floor(avg * days)
}

const selectBudget = (suggestion) => {
  selected.value = suggestion.level
  const total = calculateTotal(suggestion, props.travelDays)
  emit('select', total, suggestion.level)
}
</script>

<style scoped>
.budget-cards {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-top: 16px;
}

.budget-card {
  padding: 20px;
  border: 2px solid #e8e8e8;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.3s;
}

.budget-card:hover {
  border-color: #1890ff;
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0,0,0,0.1);
}

.budget-card.active {
  border-color: #1890ff;
  background: #e6f7ff;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.card-icon {
  font-size: 24px;
}

.card-title {
  font-size: 16px;
  font-weight: 600;
}

.daily-range {
  color: #666;
  margin-bottom: 8px;
}

.total-budget {
  color: #1890ff;
  font-weight: 600;
}
</style>
```

## 🎯 用户体验优化

### 1. 表单提示
- ✅ 必填项用红色星号标注
- ✅ 可选项明确说明"不填则自动分配"
- ✅ 提供预算档次参考

### 2. 智能建议
- ✅ 根据天数自动计算建议预算
- ✅ 提供经济/舒适/豪华三个档次
- ✅ 点击即可快速填充

### 3. 实时验证
- ✅ 预算必须 > 500元
- ✅ 每日预算 × 天数 ≤ 总预算
- ✅ 及时显示错误提示

### 4. 视觉引导
- ✅ 使用卡片式设计突出预算选择
- ✅ 悬停效果增强交互感
- ✅ 选中状态明显反馈

## ✅ 实施步骤

1. **后端验证已完成** ✓
   - 预算必填
   - 数据验证
   - 错误提示

2. **前端表单优化**
   - 添加预算必填标识
   - 添加预算建议提示
   - 添加快速选择器

3. **表单验证**
   - 前端验证逻辑
   - 错误提示优化

4. **用户引导**
   - 首次使用提示
   - 预算建议说明

这样用户在填写表单时就会被明确要求输入预算，并且有清晰的指引！
