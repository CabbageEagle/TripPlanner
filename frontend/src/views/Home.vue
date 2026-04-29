<template>
  <main class="home-page">
    <header class="home-topbar">
      <div class="brand">
        <span class="brand-mark">M</span>
        <span>智能旅行助手</span>
      </div>
      <div class="health-pill" :class="{ offline: !backendHealthy }">
        <span class="health-dot"></span>
        {{ backendHealthy ? '后端连接正常' : '后端未连接' }}
      </div>
    </header>

    <section class="hero">
      <div class="hero-copy">
        <h1>智能旅行规划助手</h1>
        <p>告诉我们你的偏好，AI 为你生成专属旅行计划</p>
      </div>
    </section>

    <section class="planner-card">
      <a-form :model="formData" layout="vertical" @finish="handleSubmit">
        <div class="form-block">
          <div class="block-title">
            <span class="block-icon pin">●</span>
            <h2>目的地和时间</h2>
          </div>

          <div class="grid destination-grid">
            <a-form-item name="city" :rules="[{ required: true, message: '请输入目的地城市' }]">
              <template #label>目的地城市</template>
              <a-input v-model:value="formData.city" placeholder="北京" size="large" />
            </a-form-item>

            <a-form-item name="start_date" :rules="[{ required: true, message: '请选择开始日期' }]">
              <template #label>开始日期</template>
              <a-date-picker
                v-model:value="formData.start_date"
                placeholder="2026-05-01"
                size="large"
                style="width: 100%"
              />
            </a-form-item>

            <a-form-item name="end_date" :rules="[{ required: true, message: '请选择结束日期' }]">
              <template #label>结束日期</template>
              <a-date-picker
                v-model:value="formData.end_date"
                placeholder="2026-05-03"
                size="large"
                style="width: 100%"
              />
            </a-form-item>

            <div class="days-counter" aria-label="旅行天数">
              <span>共</span>
              <strong>{{ formData.travel_days }}</strong>
              <span>天</span>
            </div>
          </div>
        </div>

        <div class="form-block">
          <div class="block-title">
            <span class="block-icon transport">●</span>
            <h2>旅行方式</h2>
          </div>

          <div class="choice-row">
            <span class="choice-label">交通方式</span>
            <div class="chip-grid four">
              <a-button
                v-for="option in transportationOptions"
                :key="option.value"
                html-type="button"
                class="choice-chip"
                :class="{ selected: formData.transportation === option.value }"
                @click="formData.transportation = option.value"
              >
                <span>{{ option.icon }}</span>{{ option.label }}
              </a-button>
            </div>
          </div>

          <div class="choice-row">
            <span class="choice-label">住宿偏好</span>
            <div class="chip-grid five">
              <a-button
                v-for="option in accommodationOptions"
                :key="option.value"
                html-type="button"
                class="choice-chip"
                :class="{ selected: formData.accommodation === option.value }"
                @click="formData.accommodation = option.value"
              >
                {{ option.label }}
              </a-button>
            </div>
          </div>

          <div class="choice-row">
            <span class="choice-label">兴趣偏好 <em>可多选</em></span>
            <div class="chip-grid six">
              <a-button
                v-for="option in preferenceOptions"
                :key="option"
                html-type="button"
                class="choice-chip"
                :class="{ selected: formData.preferences.includes(option) }"
                @click="togglePreference(option)"
              >
                {{ option }}
              </a-button>
            </div>
          </div>
        </div>

        <div class="form-block">
          <div class="block-title">
            <span class="block-icon budget">●</span>
            <h2>预算与时间</h2>
          </div>

          <div class="grid budget-grid">
            <a-form-item name="max_budget">
              <template #label>总预算</template>
              <a-input-number
                v-model:value="formData.max_budget"
                :min="500"
                :max="100000"
                :step="100"
                placeholder="3000"
                size="large"
                style="width: 100%"
              >
                <template #addonAfter>元</template>
              </a-input-number>
            </a-form-item>

            <a-form-item name="budget_per_day">
              <template #label>每日预算</template>
              <a-input-number
                v-model:value="formData.budget_per_day"
                :min="0"
                :max="10000"
                :step="50"
                placeholder="自动分配"
                size="large"
                style="width: 100%"
              >
                <template #addonAfter>元</template>
              </a-input-number>
            </a-form-item>

            <a-form-item name="daily_start_time">
              <template #label>每日开始时间</template>
              <a-time-picker
                v-model:value="formData.daily_start_time"
                format="HH:mm"
                placeholder="09:00"
                size="large"
                style="width: 100%"
              />
            </a-form-item>

            <a-form-item name="daily_end_time">
              <template #label>每日结束时间</template>
              <a-time-picker
                v-model:value="formData.daily_end_time"
                format="HH:mm"
                placeholder="21:00"
                size="large"
                style="width: 100%"
              />
            </a-form-item>

            <a-form-item name="max_attractions_per_day">
              <template #label>每天最多景点数</template>
              <a-input-number
                v-model:value="formData.max_attractions_per_day"
                :min="1"
                :max="10"
                placeholder="4"
                size="large"
                style="width: 100%"
              />
            </a-form-item>
          </div>

          <p class="budget-note">如果填写每日预算，总预算需大于等于“每日预算 × 天数”。</p>
        </div>

        <div class="form-block last">
          <div class="block-title">
            <span class="block-icon note">●</span>
            <h2>额外要求</h2>
          </div>

          <a-form-item name="free_text_input">
            <a-textarea
              v-model:value="formData.free_text_input"
              placeholder="想看展，少走路，不要太赶，希望体验当地特色美食。"
              :rows="4"
              :maxlength="300"
              show-count
            />
          </a-form-item>
        </div>

        <div class="submit-area">
          <a-button
            type="primary"
            html-type="submit"
            :loading="loading"
            size="large"
            class="submit-button"
          >
            {{ loading ? '正在生成旅行计划' : '生成旅行计划' }}
          </a-button>
          <p>生成将调用 AI 规划，预计需要 10-30 秒，请耐心等待</p>
        </div>

        <div v-if="loading" class="loading-card">
          <a-progress
            :percent="loadingProgress"
            status="active"
            :stroke-color="{ '0%': '#10a7a7', '100%': '#1687d9' }"
          />
          <span>{{ loadingStatus || '正在生成中...' }}</span>
        </div>
      </a-form>
    </section>
  </main>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { generateTripPlanStream, healthCheck } from '@/services/api'
import type { TripPlanStreamEvent } from '@/services/api'
import type { TripFormData } from '@/types'
import type { Dayjs } from 'dayjs'

const TRIP_PLAN_STORAGE_KEY = 'tripPlan'
const TRIP_PLAN_ID_STORAGE_KEY = 'tripPlanId'
const AGENT_DIAGNOSTICS_STORAGE_KEY = 'agentDiagnostics'

interface HomeFormState {
  city: string
  start_date: Dayjs | null
  end_date: Dayjs | null
  travel_days: number
  transportation: string
  accommodation: string
  preferences: string[]
  free_text_input: string
  max_budget?: number
  budget_per_day?: number
  daily_start_time?: Dayjs | null
  daily_end_time?: Dayjs | null
  max_attractions_per_day?: number
}

const router = useRouter()
const loading = ref(false)
const loadingProgress = ref(0)
const loadingStatus = ref('')
const backendHealthy = ref(true)

const transportationOptions = [
  { value: '公共交通', label: '公共交通', icon: '▣' },
  { value: '自驾', label: '自驾', icon: '▣' },
  { value: '步行', label: '步行', icon: '▣' },
  { value: '混合', label: '混合', icon: '▣' }
]

const accommodationOptions = [
  { value: '经济型酒店', label: '经济型' },
  { value: '舒适型酒店', label: '舒适型' },
  { value: '豪华酒店', label: '豪华型' },
  { value: '民宿', label: '民宿' },
  { value: '不住宿（当天往返）', label: '当天往返' }
]

const preferenceOptions = ['历史文化', '自然风光', '美食', '购物', '艺术', '休闲']

const formData = reactive<HomeFormState>({
  city: '',
  start_date: null,
  end_date: null,
  travel_days: 1,
  transportation: '公共交通',
  accommodation: '经济型酒店',
  preferences: [],
  free_text_input: '',
  max_budget: undefined,
  budget_per_day: undefined,
  daily_start_time: undefined,
  daily_end_time: undefined,
  max_attractions_per_day: undefined
})

onMounted(async () => {
  try {
    await healthCheck()
    backendHealthy.value = true
  } catch {
    backendHealthy.value = false
  }
})

watch([() => formData.start_date, () => formData.end_date], ([start, end]) => {
  if (start && end) {
    const days = end.diff(start, 'day') + 1
    if (days > 0 && days <= 30) {
      formData.travel_days = days
    } else if (days > 30) {
      message.warning('旅行天数不能超过30天')
      formData.end_date = null
    } else {
      message.warning('结束日期不能早于开始日期')
      formData.end_date = null
    }
  }
})

const togglePreference = (preference: string) => {
  const index = formData.preferences.indexOf(preference)
  if (index >= 0) {
    formData.preferences.splice(index, 1)
  } else {
    formData.preferences.push(preference)
  }
}

const validateBudget = (): boolean => {
  if (formData.max_budget !== undefined && formData.max_budget < 500) {
    message.error('总预算建议至少填写 500 元')
    return false
  }

  if (formData.max_budget && formData.budget_per_day) {
    const dailyTotal = formData.budget_per_day * formData.travel_days
    if (dailyTotal > formData.max_budget) {
      message.error(`每日预算 × 天数为 ${dailyTotal} 元，不能超过总预算`)
      return false
    }
  }

  return true
}

const handleSubmit = async () => {
  if (!formData.start_date || !formData.end_date) {
    message.error('请选择日期')
    return
  }

  if (!validateBudget()) {
    return
  }

  loading.value = true
  loadingProgress.value = 0
  loadingStatus.value = '正在初始化...'

  try {
    const requestData: TripFormData = {
      city: formData.city,
      start_date: formData.start_date.format('YYYY-MM-DD'),
      end_date: formData.end_date.format('YYYY-MM-DD'),
      travel_days: formData.travel_days,
      transportation: formData.transportation,
      accommodation: formData.accommodation,
      preferences: formData.preferences,
      free_text_input: formData.free_text_input,
      max_budget: formData.max_budget,
      budget_per_day: formData.budget_per_day,
      daily_start_time: formData.daily_start_time ? formData.daily_start_time.format('HH:mm') : undefined,
      daily_end_time: formData.daily_end_time ? formData.daily_end_time.format('HH:mm') : undefined,
      max_attractions_per_day: formData.max_attractions_per_day
    }

    const response = await generateTripPlanStream(requestData, (streamEvent: TripPlanStreamEvent) => {
      if (streamEvent.event !== 'progress') {
        return
      }
      const percent = Number(streamEvent.data?.percent)
      if (!Number.isNaN(percent)) {
        loadingProgress.value = Math.max(0, Math.min(100, percent))
      }
      if (typeof streamEvent.data?.message === 'string' && streamEvent.data.message.trim()) {
        loadingStatus.value = streamEvent.data.message
      }
    })

    loadingProgress.value = 100
    loadingStatus.value = '完成!'

    if (response.success && response.data) {
      sessionStorage.setItem(TRIP_PLAN_STORAGE_KEY, JSON.stringify(response.data))
      if (response.agent_diagnostics) {
        sessionStorage.setItem(AGENT_DIAGNOSTICS_STORAGE_KEY, JSON.stringify(response.agent_diagnostics))
      } else {
        sessionStorage.removeItem(AGENT_DIAGNOSTICS_STORAGE_KEY)
      }
      if (response.plan_id) {
        sessionStorage.setItem(TRIP_PLAN_ID_STORAGE_KEY, response.plan_id)
      } else {
        sessionStorage.removeItem(TRIP_PLAN_ID_STORAGE_KEY)
      }

      message.success('旅行计划生成成功')

      setTimeout(() => {
        router.push({
          path: '/result',
          query: response.plan_id ? { planId: response.plan_id } : undefined
        })
      }, 500)
    } else {
      message.error(response.message || '生成失败')
    }
  } catch (error: any) {
    message.error(error.message || '生成旅行计划失败，请稍后重试')
  } finally {
    setTimeout(() => {
      loading.value = false
      loadingProgress.value = 0
      loadingStatus.value = ''
    }, 1000)
  }
}
</script>

<style scoped>
.home-page {
  --primary: #10a7a7;
  --primary-dark: #07848c;
  --accent: #1687d9;
  --ink: #0f2342;
  --muted: #67758d;
  --line: #dce9f2;
  min-height: 100vh;
  padding: 28px 48px 42px;
  background:
    linear-gradient(180deg, rgba(230, 249, 255, 0.16) 0%, rgba(245, 251, 255, 0.96) 47%, #f5fbff 100%),
    url('../assets/hero-beijing.png') center top / 100% 410px no-repeat,
    #f5fbff;
  color: var(--ink);
}

.home-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  max-width: 1440px;
  margin: 0 auto;
  position: relative;
  z-index: 2;
}

.brand {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  font-size: 20px;
  font-weight: 800;
}

.brand-mark {
  width: 34px;
  height: 34px;
  border-radius: 12px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  background: linear-gradient(135deg, var(--primary), var(--accent));
  font-size: 16px;
}

.health-pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 38px;
  padding: 0 18px;
  border-radius: 12px;
  color: #07895f;
  background: rgba(255, 255, 255, 0.88);
  box-shadow: 0 12px 30px rgba(28, 99, 140, 0.12);
  font-size: 14px;
  font-weight: 700;
}

.health-pill.offline {
  color: #cc5b2f;
}

.health-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #17c28b;
}

.offline .health-dot {
  background: #ff7043;
}

.hero {
  max-width: 1440px;
  min-height: 250px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 10px auto 0;
  text-align: center;
}

.hero-copy h1 {
  margin: 0 0 18px;
  font-size: 46px;
  line-height: 1.08;
  letter-spacing: 0;
  color: #08254b;
  font-weight: 900;
}

.hero-copy p {
  margin: 0;
  font-size: 18px;
  color: #263b5a;
  font-weight: 500;
}

.planner-card {
  max-width: 1360px;
  margin: -2px auto 0;
  padding: 28px 32px 32px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.94);
  border: 1px solid rgba(255, 255, 255, 0.9);
  box-shadow: 0 24px 70px rgba(38, 86, 126, 0.22);
  backdrop-filter: blur(18px);
}

.form-block {
  padding: 0 0 24px;
  border-bottom: 1px solid var(--line);
  margin-bottom: 22px;
}

.form-block.last {
  margin-bottom: 0;
}

.block-title {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 18px;
}

.block-title h2 {
  margin: 0;
  font-size: 21px;
  color: var(--ink);
}

.block-icon {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 0;
  background: #e6f7fb;
  position: relative;
}

.block-icon::after {
  content: '';
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--accent);
}

.transport::after {
  background: #3298d8;
}

.budget::after {
  background: var(--primary);
}

.note::after {
  background: #2b86d9;
}

.grid {
  display: grid;
  gap: 18px 26px;
  align-items: end;
}

.destination-grid {
  grid-template-columns: 1.2fr 1fr 1fr 128px;
}

.budget-grid {
  grid-template-columns: repeat(5, minmax(150px, 1fr));
}

.days-counter {
  height: 40px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-bottom: 24px;
  color: #061b38;
  font-size: 15px;
}

.days-counter strong {
  font-size: 22px;
}

.choice-row {
  margin-top: 14px;
}

.choice-label {
  display: block;
  margin-bottom: 10px;
  color: #233653;
  font-size: 15px;
  font-weight: 700;
}

.choice-label em {
  color: #7c8aa0;
  font-style: normal;
  font-weight: 500;
  margin-left: 6px;
}

.chip-grid {
  display: grid;
  gap: 14px;
}

.chip-grid.four {
  grid-template-columns: repeat(4, minmax(118px, 1fr));
}

.chip-grid.five {
  grid-template-columns: repeat(5, minmax(108px, 1fr));
}

.chip-grid.six {
  grid-template-columns: repeat(6, minmax(96px, 1fr));
}

.choice-chip {
  height: 38px;
  border-radius: 7px;
  border-color: #cfdce8;
  color: #263b5a;
  font-weight: 700;
  background: #fff;
  box-shadow: 0 3px 10px rgba(40, 88, 128, 0.05);
}

.choice-chip span {
  margin-right: 8px;
  color: #0e9b9f;
}

.choice-chip.selected {
  border-color: var(--primary);
  color: #04858a;
  background: #eaffff;
  box-shadow: 0 6px 16px rgba(16, 167, 167, 0.13);
}

.budget-note {
  margin: 2px 0 0;
  color: var(--muted);
  font-size: 13px;
}

.submit-area {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  margin-top: 22px;
}

.submit-button {
  width: min(100%, 460px);
  height: 58px;
  border: none;
  border-radius: 999px;
  font-size: 20px;
  font-weight: 900;
  background: linear-gradient(135deg, var(--primary), #1d93e5);
  box-shadow: 0 16px 30px rgba(20, 144, 186, 0.28);
}

.submit-area p {
  margin: 0;
  color: #8a98aa;
  font-size: 13px;
}

.loading-card {
  margin: 18px auto 0;
  max-width: 520px;
  padding: 18px;
  border-radius: 12px;
  background: #f5fbff;
  border: 1px solid #dceff4;
}

.loading-card span {
  display: block;
  margin-top: 10px;
  color: #1687d9;
  text-align: center;
  font-weight: 700;
}

:deep(.ant-form-item) {
  margin-bottom: 0;
}

:deep(.ant-form-item-label > label) {
  color: #43516a;
  font-weight: 700;
}

:deep(.ant-input),
:deep(.ant-input-number),
:deep(.ant-picker),
:deep(.ant-input-affix-wrapper) {
  border-radius: 7px;
  border-color: #cfdce8;
  box-shadow: none;
}

:deep(.ant-input:hover),
:deep(.ant-input-number:hover),
:deep(.ant-picker:hover),
:deep(.ant-input:focus),
:deep(.ant-picker-focused),
:deep(.ant-input-number-focused) {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(16, 167, 167, 0.12);
}

:deep(.ant-input-number-group-addon) {
  background: #fff;
  border-color: #cfdce8;
  color: #62728a;
}

:deep(.ant-input-textarea-show-count::after) {
  color: #8998ad;
}

@media (max-width: 1100px) {
  .home-page {
    padding: 22px 22px 36px;
    background-size: auto 390px;
  }

  .destination-grid,
  .budget-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .chip-grid.four,
  .chip-grid.five,
  .chip-grid.six {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 680px) {
  .home-page {
    padding: 18px 14px 28px;
    background-size: auto 330px;
  }

  .home-topbar {
    gap: 12px;
  }

  .brand {
    font-size: 16px;
  }

  .health-pill {
    padding: 0 12px;
    font-size: 12px;
  }

  .hero {
    min-height: 210px;
  }

  .hero-copy h1 {
    font-size: 32px;
  }

  .hero-copy p {
    font-size: 15px;
  }

  .planner-card {
    padding: 22px 18px 24px;
  }

  .destination-grid,
  .budget-grid,
  .chip-grid.four,
  .chip-grid.five,
  .chip-grid.six {
    grid-template-columns: 1fr;
  }

  .days-counter {
    justify-content: flex-start;
    margin-bottom: 0;
  }
}
</style>
