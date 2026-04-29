<template>
  <main class="result-page">
    <div v-if="tripPlan" class="workspace">
      <aside class="side-nav">
        <div class="nav-top">
          <a-button class="back-button" @click="goBack">← 返回</a-button>
        </div>

        <a-menu mode="inline" :selected-keys="[activeSection]" @click="scrollToSection">
          <a-menu-item key="overview">▣ 概览</a-menu-item>
          <a-sub-menu key="days" title="▤ 每日行程">
            <a-menu-item v-for="(day, index) in tripPlan.days" :key="`day-${index}`">
              <span>第{{ day.day_index + 1 }}天</span>
              <small>{{ day.date.slice(5) }}</small>
            </a-menu-item>
          </a-sub-menu>
          <a-menu-item key="budget" v-if="tripPlan.budget || tripPlan.budget_usage">▣ 预算明细</a-menu-item>
          <a-menu-item key="conflicts" v-if="totalRiskCount > 0">
            △ 风险提醒 <span class="nav-badge">{{ totalRiskCount }}</span>
          </a-menu-item>
          <a-menu-item key="weather" v-if="tripPlan.weather_info && tripPlan.weather_info.length">☼ 天气信息</a-menu-item>
          <a-menu-item key="agent-diagnostics" v-if="agentDiagnostics">♙ Agent 诊断</a-menu-item>
        </a-menu>

        <div class="nav-tip">
          <strong>小贴士</strong>
          <span>编辑后保存会触发后端重新规划时间线。</span>
        </div>
      </aside>

      <section class="main-content">
        <header class="result-header" id="overview">
          <div>
            <div class="title-line">
              <h1>{{ tripPlan.city }} {{ tripDayCount }}日旅行计划</h1>
              <span class="saved-pill">{{ currentPlanId ? '已保存' : '本地缓存' }}</span>
            </div>
            <div class="meta-line">
              <span>{{ tripPlan.start_date }} 至 {{ tripPlan.end_date }}</span>
              <span>{{ firstDay?.transportation || '交通待定' }}</span>
              <span>{{ firstDay?.accommodation || '住宿待定' }}</span>
              <span>总预算 {{ totalBudget ? formatCurrency(totalBudget) : '未填写' }}</span>
            </div>
          </div>

          <div class="header-actions">
            <a-button v-if="!editMode" class="ghost-action" @click="toggleEditMode">编辑计划</a-button>
            <a-button v-else type="primary" class="primary-action" @click="saveChanges">保存修改</a-button>
            <a-button v-if="editMode" class="ghost-action" @click="cancelEdit">取消编辑</a-button>
            <a-dropdown v-if="!editMode">
              <template #overlay>
                <a-menu>
                  <a-menu-item key="image" @click="exportAsImage">导出为图片</a-menu-item>
                  <a-menu-item key="pdf" @click="exportAsPDF">导出为 PDF</a-menu-item>
                </a-menu>
              </template>
              <a-button type="primary" class="export-action">导出 <DownOutlined /></a-button>
            </a-dropdown>
          </div>
        </header>

        <section class="metric-grid">
          <article class="metric-card">
            <span class="metric-label">总费用</span>
            <strong>{{ formatCurrency(totalCost) }}</strong>
            <div class="metric-foot">
              <span>预算 {{ totalBudget ? formatCurrency(totalBudget) : '未填写' }}</span>
              <span v-if="totalBudget">{{ getBudgetUsagePercent() }}%</span>
            </div>
            <a-progress v-if="totalBudget" :percent="getBudgetUsagePercent()" :show-info="false" />
          </article>

          <article class="metric-card">
            <span class="metric-label">景点数量</span>
            <strong>{{ totalAttractions }} <small>个</small></strong>
            <div class="metric-foot">平均每天 {{ averageAttractions }} 个</div>
            <div class="metric-blob green">◆</div>
          </article>

          <article class="metric-card risk">
            <span class="metric-label">风险提醒</span>
            <strong>{{ totalRiskCount }} <small>条</small></strong>
            <div class="metric-foot">{{ criticalRiskCount }} 个严重风险</div>
            <div class="metric-blob orange">!</div>
          </article>

          <article class="metric-card">
            <span class="metric-label">天气概览</span>
            <strong>{{ weatherSummary }}</strong>
            <div class="metric-foot">{{ todayWeather?.day_weather || '暂无天气数据' }}</div>
            <div class="metric-blob sky weather-emoji">{{ weatherIcon }}</div>
          </article>
        </section>

        <section class="overview-card">
          <div class="timeline-panel">
            <div class="panel-head">
              <h2>第{{ (activeTimelineDay?.day_index ?? 0) + 1 }}天</h2>
              <span>{{ activeTimelineDay?.date || tripPlan.start_date }}</span>
            </div>

            <div v-if="visibleTimeline.length" class="timeline-list">
              <div v-for="(item, index) in visibleTimeline" :key="`${item.start_time}-${index}`" class="timeline-row">
                <span class="timeline-dot"></span>
                <time>{{ item.start_time }}</time>
                <div class="timeline-copy">
                  <strong>{{ item.activity_name }}</strong>
                  <span>{{ getActivityDescription(item) }}</span>
                  <small v-if="item.cost && item.cost > 0">{{ formatCurrency(item.cost) }}</small>
                </div>
                <img :src="getActivityImage(item.activity_name, index)" :alt="item.activity_name" @error="handleImageError" />
              </div>
            </div>
            <a-empty v-else description="暂无时间线" />

            <div v-if="tripPlan.days.length > 1" class="timeline-day-actions">
              <a-button v-if="activeTimelineDayIndex > 0" class="next-day-button" @click="showTimelineDay(activeTimelineDayIndex - 1)">
                查看第{{ activeTimelineDayIndex }}天行程 ↑
              </a-button>
              <a-button v-if="activeTimelineDayIndex < tripPlan.days.length - 1" class="next-day-button" @click="showTimelineDay(activeTimelineDayIndex + 1)">
                查看第{{ activeTimelineDayIndex + 2 }}天行程 ↓
              </a-button>
            </div>
          </div>

          <div class="map-panel" id="map">
            <div class="panel-head">
              <h2>行程地图</h2>
              <div class="map-tabs">
                <span>景点</span>
                <span>交通</span>
              </div>
            </div>
            <div id="amap-container"></div>
          </div>
        </section>

        <section class="recommend-section">
          <div class="section-title">精选推荐 ›</div>
          <div class="recommend-grid">
            <article v-for="item in recommendationCards" :key="item.title" class="recommend-card" :class="item.tone">
              <strong>{{ item.title }}</strong>
              <span>{{ item.count }}</span>
              <small>{{ item.desc }}</small>
              <b>{{ item.icon }}</b>
            </article>
          </div>
        </section>

        <section id="conflicts" class="bottom-grid" v-if="totalRiskCount > 0 || todayWeather || agentDiagnostics">
          <article v-if="totalRiskCount > 0" class="info-card wide">
            <div class="section-title">风险提醒 <small>({{ totalRiskCount }})</small></div>
            <div class="risk-list">
              <div v-for="(warning, index) in tripPlan.warnings || []" :key="`warning-${index}`" class="risk-row">
                <a-tag color="orange">警告</a-tag>
                <span>{{ warning }}</span>
              </div>
              <div v-for="(item, index) in tripPlan.time_conflicts || []" :key="`conflict-${index}`" class="risk-row">
                <a-tag :color="getConflictTagColor(item.severity)">{{ item.severity }}</a-tag>
                <span>{{ item.description }}</span>
                <small v-if="item.day_index !== null && item.day_index !== undefined">第{{ item.day_index + 1 }}天</small>
              </div>
            </div>
          </article>

          <article id="weather" v-if="todayWeather" class="info-card weather-card">
            <div class="section-title">今日天气 <small>{{ todayWeather.date.slice(5) }}</small></div>
            <strong>{{ normalizeTemp(todayWeather.day_temp) }}°C</strong>
            <span>{{ todayWeather.day_weather }}</span>
            <small>{{ normalizeTemp(todayWeather.night_temp) }}°C - {{ normalizeTemp(todayWeather.day_temp) }}°C</small>
          </article>

          <article v-if="agentDiagnostics" class="info-card agent-card">
            <div class="section-title">Agent 诊断</div>
            <span>{{ agentDiagnostics.ready_for_planning ? '已折叠' : '需关注' }}</span>
            <small>点击展开查看 AI 分析和规划过程</small>
            <a-button shape="circle" @click="scrollToSection({ key: 'agent-diagnostics' })">›</a-button>
          </article>
        </section>

        <section id="daily" class="daily-section">
          <div class="section-title">每日行程</div>
          <a-alert
            v-if="editMode"
            type="warning"
            show-icon
            message="编辑景点顺序或删除景点后，保存会由后端重新排程。"
            class="edit-alert"
          />

          <a-collapse v-model:activeKey="activeDays" accordion>
            <a-collapse-panel v-for="(day, dayIndex) in tripPlan.days" :key="dayIndex" :id="`day-${dayIndex}`">
              <template #header>
                <div class="day-header">
                  <strong>第{{ day.day_index + 1 }}天</strong>
                  <span>{{ day.date }}</span>
                  <small>{{ day.attractions.length }} 个景点</small>
                </div>
              </template>

              <div class="day-summary">
                <span>{{ day.description }}</span>
                <span>交通：{{ day.transportation }}</span>
                <span>住宿：{{ day.accommodation }}</span>
                <span v-if="day.total_cost !== undefined">费用：{{ formatCurrency(day.total_cost) }}</span>
              </div>

              <div class="attraction-grid">
                <article v-for="(item, index) in day.attractions" :key="`${day.day_index}-${item.name}-${index}`" class="attraction-card">
                  <img :src="getAttractionImage(item.name, index, item.image_url)" :alt="item.name" @error="handleImageError" />
                  <div>
                    <div class="attraction-title">
                      <strong>{{ item.name }}</strong>
                      <span v-if="item.ticket_price !== undefined">{{ formatCurrency(item.ticket_price) }}</span>
                    </div>
                    <p>{{ item.description }}</p>
                    <small>{{ item.address }} · 建议游览 {{ item.visit_duration }} 分钟</small>
                    <div v-if="editMode" class="edit-actions">
                      <a-button size="small" @click="moveAttraction(day.day_index, index, 'up')" :disabled="index === 0">上移</a-button>
                      <a-button size="small" @click="moveAttraction(day.day_index, index, 'down')" :disabled="index === day.attractions.length - 1">下移</a-button>
                      <a-button size="small" danger @click="deleteAttraction(day.day_index, index)">删除</a-button>
                    </div>
                  </div>
                </article>
              </div>

              <div v-if="day.meals && day.meals.length" class="meal-grid">
                <article v-for="meal in day.meals" :key="`${day.day_index}-${meal.type}-${meal.name}`">
                  <strong>{{ getMealLabel(meal.type) }} · {{ meal.name }}</strong>
                  <span>{{ meal.description || meal.address || '餐饮推荐' }}</span>
                  <small v-if="meal.estimated_cost">{{ formatCurrency(meal.estimated_cost) }}</small>
                </article>
              </div>
            </a-collapse-panel>
          </a-collapse>
        </section>

        <section id="budget" v-if="tripPlan.budget || tripPlan.budget_usage" class="budget-section">
          <div class="section-title">预算明细</div>
          <div class="budget-detail-grid">
            <article v-if="tripPlan.budget" class="budget-detail-card">
              <span>景点门票</span><strong>{{ formatCurrency(tripPlan.budget.total_attractions) }}</strong>
            </article>
            <article v-if="tripPlan.budget" class="budget-detail-card">
              <span>酒店住宿</span><strong>{{ formatCurrency(tripPlan.budget.total_hotels) }}</strong>
            </article>
            <article v-if="tripPlan.budget" class="budget-detail-card">
              <span>餐饮费用</span><strong>{{ formatCurrency(tripPlan.budget.total_meals) }}</strong>
            </article>
            <article v-if="tripPlan.budget" class="budget-detail-card">
              <span>交通费用</span><strong>{{ formatCurrency(tripPlan.budget.total_transportation) }}</strong>
            </article>
            <article v-if="tripPlan.budget_usage" class="budget-detail-card total">
              <span>剩余预算</span><strong>{{ formatCurrency(tripPlan.budget_usage.remaining_budget) }}</strong>
            </article>
          </div>
        </section>

        <section id="agent-diagnostics" v-if="agentDiagnostics" class="diagnostics-section">
          <a-collapse>
            <a-collapse-panel key="diagnostics" header="Agent 诊断">
              <div class="diagnostics-summary">
                <a-tag :color="agentDiagnostics.ready_for_planning ? 'green' : 'orange'">
                  {{ agentDiagnostics.ready_for_planning ? '已满足规划前置条件' : '规划前置条件未完全满足' }}
                </a-tag>
                <a-tag :color="agentDiagnostics.router_warning ? 'orange' : 'green'">
                  {{ agentDiagnostics.router_warning ? '发生 router_warning' : '无 router_warning' }}
                </a-tag>
                <a-tag :color="agentDiagnostics.forced_exit ? 'red' : 'green'">
                  {{ agentDiagnostics.forced_exit ? '发生 forced_exit' : '无 forced_exit' }}
                </a-tag>
              </div>

              <a-alert
                v-if="agentDiagnostics.context_summary"
                type="info"
                show-icon
                :message="agentDiagnostics.context_summary"
                class="diagnostics-alert"
              />

              <a-descriptions title="SOP 必查项" :column="2" size="small" bordered>
                <a-descriptions-item v-for="item in sopDiagnostics" :key="item.key" :label="item.label">
                  <a-tag :color="item.required ? 'blue' : 'default'">{{ item.required ? '必查' : '非必查' }}</a-tag>
                  <a-tag :color="item.completed ? 'green' : 'orange'">{{ item.completed ? '已完成' : '未完成' }}</a-tag>
                </a-descriptions-item>
              </a-descriptions>

              <a-divider orientation="left">工具调用</a-divider>
              <a-list
                v-if="agentDiagnostics.tool_calls && agentDiagnostics.tool_calls.length > 0"
                :data-source="agentDiagnostics.tool_calls"
                size="small"
                bordered
              >
                <template #renderItem="{ item, index }">
                  <a-list-item>
                    <a-space direction="vertical" size="small" style="width: 100%">
                      <a-space wrap>
                        <a-tag color="blue">#{{ index + 1 }}</a-tag>
                        <strong>{{ getToolLabel(item.tool_name) }}</strong>
                        <a-tag :color="item.success ? 'green' : 'red'">
                          {{ item.success ? '成功' : '失败 / fallback' }}
                        </a-tag>
                        <a-tag>结果 {{ item.result_count || 0 }} 条</a-tag>
                      </a-space>
                      <span v-if="item.reason"><strong>调用原因:</strong> {{ truncateText(item.reason, 180) }}</span>
                      <span v-if="item.summary"><strong>结果摘要:</strong> {{ truncateText(item.summary) }}</span>
                    </a-space>
                  </a-list-item>
                </template>
              </a-list>
              <a-empty v-else description="本次没有工具调用记录" />
            </a-collapse-panel>
          </a-collapse>
        </section>
      </section>
    </div>

    <a-empty v-else class="empty-state" description="没有找到旅行计划数据">
      <template #image>
        <div class="empty-icon">◎</div>
      </template>
      <template #description>
        <span>暂无旅行计划数据，请先创建行程</span>
      </template>
      <a-button type="primary" @click="goBack">返回首页创建行程</a-button>
    </a-empty>

    <a-back-top :visibility-height="300">
      <div class="back-top-button">↑</div>
    </a-back-top>
  </main>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { DownOutlined } from '@ant-design/icons-vue'
import AMapLoader from '@amap/amap-jsapi-loader'
import { API_BASE_URL, getTripPlan, updateTripPlan } from '@/services/api'
import type { AgentDiagnostics, TripPlan, TimelineItem } from '@/types'

const TRIP_PLAN_STORAGE_KEY = 'tripPlan'
const TRIP_PLAN_ID_STORAGE_KEY = 'tripPlanId'
const AGENT_DIAGNOSTICS_STORAGE_KEY = 'agentDiagnostics'

const router = useRouter()
const route = useRoute()
const tripPlan = ref<TripPlan | null>(null)
const agentDiagnostics = ref<AgentDiagnostics | null>(null)
const currentPlanId = ref<string | null>(null)
const editMode = ref(false)
const originalPlan = ref<TripPlan | null>(null)
const attractionPhotos = ref<Record<string, string>>({})
const placeholderImages = new Map<string, string>()
const activeSection = ref('overview')
const activeDays = ref<number[]>([0])
const activeTimelineDayIndex = ref(0)
let map: any = null

const tripDayCount = computed(() => tripPlan.value?.days.length || 0)
const firstDay = computed(() => tripPlan.value?.days[0] || null)
const activeTimelineDay = computed(() => {
  if (!tripPlan.value?.days.length) return null
  const safeIndex = Math.min(Math.max(activeTimelineDayIndex.value, 0), tripPlan.value.days.length - 1)
  return tripPlan.value.days[safeIndex] || null
})
const todayWeather = computed(() => tripPlan.value?.weather_info?.[0] || null)
const totalBudget = computed(() => tripPlan.value?.budget_usage?.total_budget || null)
const totalCost = computed(() => {
  if (tripPlan.value?.budget?.total !== undefined) {
    return tripPlan.value.budget.total
  }
  return tripPlan.value?.days.reduce((sum, day) => sum + (day.total_cost || 0), 0) || 0
})
const totalAttractions = computed(() => tripPlan.value?.days.reduce((sum, day) => sum + day.attractions.length, 0) || 0)
const averageAttractions = computed(() => {
  if (!tripDayCount.value) return 0
  return Math.round(totalAttractions.value / tripDayCount.value)
})
const totalRiskCount = computed(() => (tripPlan.value?.warnings?.length || 0) + (tripPlan.value?.time_conflicts?.length || 0))
const criticalRiskCount = computed(() => tripPlan.value?.time_conflicts?.filter(item => item.severity === 'critical').length || 0)
const weatherSummary = computed(() => {
  if (!todayWeather.value) return '--'
  return `${normalizeTemp(todayWeather.value.night_temp)}°C / ${normalizeTemp(todayWeather.value.day_temp)}°C`
})
const weatherIcon = computed(() => {
  const text = `${todayWeather.value?.day_weather || ''}${todayWeather.value?.night_weather || ''}`
  if (!text) return '☼'
  if (text.includes('雷')) return '⛈'
  if (text.includes('雨')) return '🌧'
  if (text.includes('雪')) return '❄'
  if (text.includes('阴')) return '☁'
  if (text.includes('多云')) return '⛅'
  if (text.includes('晴')) return '☀'
  return '☼'
})
const visibleTimeline = computed<TimelineItem[]>(() => {
  const day = activeTimelineDay.value
  if (!day) return []
  if (day.timeline && day.timeline.length) return day.timeline
  return day.attractions.map(attraction => ({
    start_time: attraction.visit_start_time || '--:--',
    end_time: attraction.visit_end_time || '--:--',
    activity_type: 'attraction',
    activity_name: attraction.name,
    duration: attraction.visit_duration,
    location: attraction.location,
    cost: attraction.ticket_price || 0
  }))
})
const recommendationCards = computed(() => {
  const hotelCount = tripPlan.value?.days.filter(day => day.hotel).length || 0
  const mealCount = tripPlan.value?.days.reduce((sum, day) => sum + (day.meals?.length || 0), 0) || 0
  return [
    { title: '景点推荐', count: `${totalAttractions.value} 个景点`, desc: '历史文化与自然风光', icon: '▲', tone: 'blue' },
    { title: '酒店推荐', count: `${hotelCount} 家酒店`, desc: '舒适型为主', icon: '▣', tone: 'purple' },
    { title: '美食推荐', count: `${mealCount} 家餐厅`, desc: '地道美食体验', icon: '∥', tone: 'orange' },
    { title: '购物推荐', count: '3 个地点', desc: '特色购物体验', icon: '▤', tone: 'pink' }
  ]
})

const persistTripPlanCache = (plan: TripPlan, planId?: string | null, diagnostics?: AgentDiagnostics | null) => {
  sessionStorage.setItem(TRIP_PLAN_STORAGE_KEY, JSON.stringify(plan))
  if (diagnostics) {
    sessionStorage.setItem(AGENT_DIAGNOSTICS_STORAGE_KEY, JSON.stringify(diagnostics))
  } else if (diagnostics === null) {
    sessionStorage.removeItem(AGENT_DIAGNOSTICS_STORAGE_KEY)
  }
  if (planId) {
    sessionStorage.setItem(TRIP_PLAN_ID_STORAGE_KEY, planId)
  }
}

const resolvePlanId = (): string | null => {
  const queryPlanId = typeof route.query.planId === 'string' ? route.query.planId : null
  return queryPlanId || sessionStorage.getItem(TRIP_PLAN_ID_STORAGE_KEY)
}

const rebuildMap = () => {
  if (map) {
    map.destroy()
    map = null
  }
  nextTick(() => {
    initMap()
  })
}

const sopLabels: Record<string, string> = {
  attractions_required: '景点信息',
  weather_required: '天气信息',
  hotels_required: '酒店信息',
  transit_required: '交通测算',
  local_events_optional: '本地活动增强'
}

const completedKeyByRequiredKey: Record<string, string> = {
  attractions_required: 'attractions_done',
  weather_required: 'weather_done',
  hotels_required: 'hotels_done',
  transit_required: 'transit_done'
}

const sopDiagnostics = computed(() => {
  const required = agentDiagnostics.value?.sop_required || {}
  const completed = agentDiagnostics.value?.sop_completed || {}
  return Object.entries(sopLabels).map(([key, label]) => {
    const completedKey = completedKeyByRequiredKey[key]
    return {
      key,
      label,
      required: Boolean(required[key]),
      completed: completedKey ? Boolean(completed[completedKey]) : Boolean(required[key])
    }
  })
})

const getToolLabel = (toolName: string): string => {
  const labels: Record<string, string> = {
    search_attractions_tool: '搜索景点',
    query_weather_tool: '查询天气',
    search_hotels_tool: '搜索酒店',
    search_local_events_tool: '搜索本地活动',
    estimate_transit_time_tool: '估算交通时间'
  }
  return labels[toolName] || toolName || '未知工具'
}

const truncateText = (value: unknown, maxLength = 240): string => {
  const text = String(value || '').replace(/\s+/g, ' ').trim()
  if (text.length <= maxLength) {
    return text
  }
  return `${text.slice(0, maxLength)}...`
}

const loadPersistedTripPlan = async () => {
  const planId = resolvePlanId()
  const cachedPlan = sessionStorage.getItem(TRIP_PLAN_STORAGE_KEY)
  const cachedDiagnostics = sessionStorage.getItem(AGENT_DIAGNOSTICS_STORAGE_KEY)

  if (planId) {
    currentPlanId.value = planId
    try {
      const response = await getTripPlan(planId)
      if (response.success && response.data) {
        tripPlan.value = response.data
        agentDiagnostics.value = response.agent_diagnostics || null
        persistTripPlanCache(response.data, response.plan_id || planId, response.agent_diagnostics || null)
        return
      }
      throw new Error(response.message || '获取旅行计划失败')
    } catch (error: any) {
      console.error('获取已保存旅行计划失败:', error)
      if (cachedPlan) {
        message.warning('读取云端行程失败，已使用本地缓存')
      }
    }
  }

  if (cachedPlan) {
    tripPlan.value = JSON.parse(cachedPlan)
    currentPlanId.value = planId
    if (cachedDiagnostics) {
      agentDiagnostics.value = JSON.parse(cachedDiagnostics)
    }
  }
}

onMounted(async () => {
  await loadPersistedTripPlan()
  if (tripPlan.value) {
    await nextTick()
    initMap()
    void loadAttractionPhotos()
  }
})

const goBack = () => {
  router.push('/')
}

const scrollToSection = ({ key }: { key: string }) => {
  activeSection.value = key
  const element = document.getElementById(key)
  if (element) {
    element.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
}

const showTimelineDay = (index: number) => {
  if (!tripPlan.value?.days.length) return
  const safeIndex = Math.min(Math.max(index, 0), tripPlan.value.days.length - 1)
  activeTimelineDayIndex.value = safeIndex
  activeDays.value = [safeIndex]
}

const toggleEditMode = () => {
  editMode.value = true
  originalPlan.value = JSON.parse(JSON.stringify(tripPlan.value))
  message.info('进入编辑模式')
}

const saveChanges = async () => {
  if (!tripPlan.value) return

  try {
    if (currentPlanId.value) {
      const response = await updateTripPlan(currentPlanId.value, tripPlan.value, '前端编辑保存')
      if (!response.success || !response.data) {
        throw new Error(response.message || '保存旅行计划失败')
      }
      tripPlan.value = response.data
      agentDiagnostics.value = response.agent_diagnostics || agentDiagnostics.value
      persistTripPlanCache(response.data, response.plan_id || currentPlanId.value, agentDiagnostics.value)
    } else {
      persistTripPlanCache(tripPlan.value, null, agentDiagnostics.value)
    }

    editMode.value = false
    message.success('修改已保存')
    rebuildMap()
  } catch (error: any) {
    message.error(error.message || '保存旅行计划失败，请稍后重试')
  }
}

const cancelEdit = () => {
  if (originalPlan.value) {
    tripPlan.value = JSON.parse(JSON.stringify(originalPlan.value))
  }
  editMode.value = false
  message.info('已取消编辑')
}

const deleteAttraction = (dayIndex: number, attrIndex: number) => {
  if (!tripPlan.value) return

  const day = tripPlan.value.days[dayIndex]
  if (!day || day.attractions.length <= 1) {
    message.warning('每天至少需要保留一个景点')
    return
  }

  day.attractions.splice(attrIndex, 1)
  message.success('景点已删除')
}

const moveAttraction = (dayIndex: number, attrIndex: number, direction: 'up' | 'down') => {
  if (!tripPlan.value) return

  const day = tripPlan.value.days[dayIndex]
  if (!day) return
  const attractions = day.attractions

  if (direction === 'up' && attrIndex > 0) {
    ;[attractions[attrIndex], attractions[attrIndex - 1]] = [attractions[attrIndex - 1], attractions[attrIndex]]
  } else if (direction === 'down' && attrIndex < attractions.length - 1) {
    ;[attractions[attrIndex], attractions[attrIndex + 1]] = [attractions[attrIndex + 1], attractions[attrIndex]]
  }
}

const getMealLabel = (type: string): string => {
  const labels: Record<string, string> = {
    breakfast: '早餐',
    lunch: '午餐',
    dinner: '晚餐',
    snack: '小吃'
  }
  return labels[type] || type
}

const formatCurrency = (value?: number | null): string => {
  if (value === undefined || value === null || Number.isNaN(Number(value))) {
    return '¥--'
  }
  return `¥${Number(value).toLocaleString('zh-CN')}`
}

const normalizeTemp = (value: number | string): number => {
  if (typeof value === 'number') return value
  const parsed = Number(String(value).replace(/[^\d-]/g, ''))
  return Number.isNaN(parsed) ? 0 : parsed
}

const getActivityDescription = (item: TimelineItem): string => {
  const attraction = activeTimelineDay.value?.attractions.find(entry => entry.name === item.activity_name)
  if (attraction?.category) {
    return `${attraction.category} · 建议游览 ${attraction.visit_duration || item.duration} 分钟`
  }
  if (item.activity_type === 'meal') {
    return '餐饮安排'
  }
  return `建议游览 ${item.duration} 分钟`
}

const getBudgetUsagePercent = (): number => {
  if (!tripPlan.value?.budget_usage) return 0
  const { total_budget, used_budget } = tripPlan.value.budget_usage
  if (!total_budget || total_budget <= 0) return 0
  return Math.min(100, Math.round((used_budget / total_budget) * 100))
}

const getConflictTagColor = (severity: string): string => {
  if (severity === 'critical') return 'red'
  if (severity === 'warning') return 'orange'
  return 'blue'
}

const loadAttractionPhotos = async () => {
  if (!tripPlan.value) return

  attractionPhotos.value = {}
  const names = Array.from(
    new Set(
      tripPlan.value.days.flatMap(day => day.attractions.map(attraction => attraction.name).filter(Boolean))
    )
  )

  const batchSize = 4
  for (let index = 0; index < names.length; index += batchSize) {
    const batch = names.slice(index, index + batchSize)
    await Promise.all(
      batch.map(name =>
        fetch(`${API_BASE_URL}/api/poi/photo?name=${encodeURIComponent(name)}`)
        .then(res => res.json())
        .then(data => {
          if (data.success && data.data.photo_url) {
            attractionPhotos.value[name] = data.data.photo_url
          }
        })
        .catch(err => {
          console.error(`获取${name}图片失败:`, err)
        })
      )
    )
  }
}

const getActivityImage = (activityName: string, index: number): string => {
  const attraction = tripPlan.value?.days
    .flatMap(day => day.attractions)
    .find(item => item.name === activityName)
  return getAttractionImage(activityName, index, attraction?.image_url)
}

const getAttractionImage = (name: string, index: number, imageUrl?: string): string => {
  if (imageUrl) {
    return imageUrl
  }
  if (attractionPhotos.value[name]) {
    return attractionPhotos.value[name]
  }
  const cacheKey = `${name}-${index}`
  const cached = placeholderImages.get(cacheKey)
  if (cached) {
    return cached
  }

  const colors = [
    { start: '#bdeeff', end: '#1687d9' },
    { start: '#dff7ef', end: '#10a7a7' },
    { start: '#fff0db', end: '#ff9f68' },
    { start: '#eef2ff', end: '#8a9cf2' },
    { start: '#ffe5ed', end: '#f4729a' }
  ]
  const colorIndex = index % colors.length
  const { start, end } = colors[colorIndex]

  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="400" height="260">
    <defs>
      <linearGradient id="grad${index}" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" style="stop-color:${start};stop-opacity:1" />
        <stop offset="100%" style="stop-color:${end};stop-opacity:1" />
      </linearGradient>
    </defs>
    <rect width="400" height="260" rx="24" fill="url(#grad${index})"/>
    <circle cx="316" cy="72" r="38" fill="rgba(255,255,255,.45)"/>
    <path d="M72 170 L142 98 L204 160 L245 124 L330 204 L72 204 Z" fill="rgba(255,255,255,.58)"/>
    <text x="50%" y="52%" dominant-baseline="middle" text-anchor="middle" font-family="Microsoft YaHei, sans-serif" font-size="24" font-weight="700" fill="#0f2342">${name}</text>
  </svg>`

  const dataUrl = `data:image/svg+xml;base64,${btoa(unescape(encodeURIComponent(svg)))}`
  placeholderImages.set(cacheKey, dataUrl)
  return dataUrl
}

const handleImageError = (event: Event) => {
  const img = event.target as HTMLImageElement
  img.src = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="400" height="260"%3E%3Crect width="400" height="260" rx="20" fill="%23edf6fb"/%3E%3Ctext x="50%25" y="50%25" dominant-baseline="middle" text-anchor="middle" font-family="sans-serif" font-size="18" fill="%23778aa2"%3E图片加载失败%3C/text%3E%3C/svg%3E'
}

const exportAsImage = async () => {
  try {
    message.loading({ content: '正在生成图片...', key: 'export', duration: 0 })
    const { default: html2canvas } = await import('html2canvas')

    const element = document.querySelector('.main-content') as HTMLElement
    if (!element) {
      throw new Error('未找到内容元素')
    }

    const exportContainer = document.createElement('div')
    exportContainer.style.width = element.offsetWidth + 'px'
    exportContainer.style.backgroundColor = '#f5fbff'
    exportContainer.style.padding = '20px'
    exportContainer.innerHTML = element.innerHTML

    const mapContainer = document.getElementById('amap-container')
    if (mapContainer && map) {
      const mapCanvas = mapContainer.querySelector('canvas')
      if (mapCanvas) {
        const mapSnapshot = mapCanvas.toDataURL('image/png')
        const exportMapContainer = exportContainer.querySelector('#amap-container')
        if (exportMapContainer) {
          exportMapContainer.innerHTML = `<img src="${mapSnapshot}" style="width:100%;height:100%;object-fit:cover;" />`
        }
      }
    }

    exportContainer.style.position = 'absolute'
    exportContainer.style.left = '-9999px'
    document.body.appendChild(exportContainer)

    const canvas = await html2canvas(exportContainer, {
      backgroundColor: '#f5fbff',
      scale: 2,
      logging: false,
      useCORS: true,
      allowTaint: true
    })

    document.body.removeChild(exportContainer)

    const link = document.createElement('a')
    link.download = `旅行计划_${tripPlan.value?.city}_${new Date().getTime()}.png`
    link.href = canvas.toDataURL('image/png')
    link.click()

    message.success({ content: '图片导出成功', key: 'export' })
  } catch (error: any) {
    console.error('导出图片失败:', error)
    message.error({ content: `导出图片失败: ${error.message}`, key: 'export' })
  }
}

const exportAsPDF = async () => {
  try {
    message.loading({ content: '正在生成PDF...', key: 'export', duration: 0 })
    const [{ default: html2canvas }, { default: jsPDF }] = await Promise.all([
      import('html2canvas'),
      import('jspdf')
    ])

    const element = document.querySelector('.main-content') as HTMLElement
    if (!element) {
      throw new Error('未找到内容元素')
    }

    const exportContainer = document.createElement('div')
    exportContainer.style.width = element.offsetWidth + 'px'
    exportContainer.style.backgroundColor = '#f5fbff'
    exportContainer.style.padding = '20px'
    exportContainer.innerHTML = element.innerHTML

    const mapContainer = document.getElementById('amap-container')
    if (mapContainer && map) {
      const mapCanvas = mapContainer.querySelector('canvas')
      if (mapCanvas) {
        const mapSnapshot = mapCanvas.toDataURL('image/png')
        const exportMapContainer = exportContainer.querySelector('#amap-container')
        if (exportMapContainer) {
          exportMapContainer.innerHTML = `<img src="${mapSnapshot}" style="width:100%;height:100%;object-fit:cover;" />`
        }
      }
    }

    exportContainer.style.position = 'absolute'
    exportContainer.style.left = '-9999px'
    document.body.appendChild(exportContainer)

    const canvas = await html2canvas(exportContainer, {
      backgroundColor: '#f5fbff',
      scale: 2,
      logging: false,
      useCORS: true,
      allowTaint: true
    })

    document.body.removeChild(exportContainer)

    const imgData = canvas.toDataURL('image/png')
    const pdf = new jsPDF({
      orientation: 'portrait',
      unit: 'mm',
      format: 'a4'
    })

    const imgWidth = 210
    const imgHeight = (canvas.height * imgWidth) / canvas.width

    let heightLeft = imgHeight
    let position = 0

    pdf.addImage(imgData, 'PNG', 0, position, imgWidth, imgHeight)
    heightLeft -= 297

    while (heightLeft > 0) {
      position = heightLeft - imgHeight
      pdf.addPage()
      pdf.addImage(imgData, 'PNG', 0, position, imgWidth, imgHeight)
      heightLeft -= 297
    }

    pdf.save(`旅行计划_${tripPlan.value?.city}_${new Date().getTime()}.pdf`)

    message.success({ content: 'PDF导出成功', key: 'export' })
  } catch (error: any) {
    console.error('导出PDF失败:', error)
    message.error({ content: `导出PDF失败: ${error.message}`, key: 'export' })
  }
}

const initMap = async () => {
  try {
    const AMap = await AMapLoader.load({
      key: import.meta.env.VITE_AMAP_WEB_JS_KEY,
      version: '2.0',
      plugins: ['AMap.Marker', 'AMap.Polyline', 'AMap.InfoWindow']
    })

    map = new AMap.Map('amap-container', {
      zoom: 12,
      center: [116.397128, 39.916527],
      viewMode: '3D'
    })

    addAttractionMarkers(AMap)
  } catch (error) {
    console.error('地图加载失败:', error)
    message.error('地图加载失败')
  }
}

const addAttractionMarkers = (AMap: any) => {
  if (!tripPlan.value || !map) return

  const markers: any[] = []
  const allAttractions: any[] = []

  tripPlan.value.days.forEach((day, dayIndex) => {
    day.attractions.forEach((attraction, attrIndex) => {
      if (attraction.location && attraction.location.longitude && attraction.location.latitude) {
        allAttractions.push({
          ...attraction,
          dayIndex,
          attrIndex
        })
      }
    })
  })

  allAttractions.forEach((attraction, index) => {
    const marker = new AMap.Marker({
      position: [attraction.location.longitude, attraction.location.latitude],
      title: attraction.name,
      label: {
        content: `<div style="background:#10a7a7;color:white;padding:4px 8px;border-radius:999px;font-size:12px;font-weight:700;">${index + 1}</div>`,
        offset: new AMap.Pixel(0, -30)
      }
    })

    const infoWindow = new AMap.InfoWindow({
      content: `
        <div style="padding:10px;max-width:240px;">
          <h4 style="margin:0 0 8px 0;">${attraction.name}</h4>
          <p style="margin:4px 0;"><strong>地址:</strong> ${attraction.address}</p>
          <p style="margin:4px 0;"><strong>游览时长:</strong> ${attraction.visit_duration}分钟</p>
          <p style="margin:4px 0;color:#1687d9;"><strong>第${attraction.dayIndex + 1}天 景点${attraction.attrIndex + 1}</strong></p>
        </div>
      `,
      offset: new AMap.Pixel(0, -30)
    })

    marker.on('click', () => {
      infoWindow.open(map, marker.getPosition())
    })

    markers.push(marker)
  })

  map.add(markers)

  if (allAttractions.length > 0) {
    map.setFitView(markers)
  }

  drawRoutes(AMap, allAttractions)
}

const drawRoutes = (AMap: any, attractions: any[]) => {
  if (!map || attractions.length < 2) return

  const dayGroups: Record<string, any[]> = {}
  attractions.forEach(attr => {
    if (!dayGroups[attr.dayIndex]) {
      dayGroups[attr.dayIndex] = []
    }
    dayGroups[attr.dayIndex].push(attr)
  })

  Object.values(dayGroups).forEach(dayAttractions => {
    if (dayAttractions.length < 2) return

    const path = dayAttractions.map(attr => [attr.location.longitude, attr.location.latitude])

    const polyline = new AMap.Polyline({
      path,
      strokeColor: '#1687d9',
      strokeWeight: 5,
      strokeOpacity: 0.82,
      strokeStyle: 'solid',
      showDir: true
    })

    map.add(polyline)
  })
}
</script>

<style scoped>
.result-page {
  --primary: #10a7a7;
  --accent: #1687d9;
  --danger: #ff7043;
  --ink: #0f2342;
  --muted: #68778f;
  --line: #e0ebf3;
  --surface: #ffffff;
  min-height: 100vh;
  background:
    radial-gradient(circle at 12% 8%, rgba(31, 190, 198, 0.12), transparent 30%),
    linear-gradient(180deg, #f8fcff 0%, #f2f9fd 100%);
  color: var(--ink);
}

.workspace {
  display: grid;
  grid-template-columns: 250px minmax(0, 1fr);
  min-height: 100vh;
}

.side-nav {
  position: sticky;
  top: 0;
  height: 100vh;
  padding: 36px 20px 24px;
  background: rgba(255, 255, 255, 0.82);
  border-right: 1px solid #e5eef5;
  box-shadow: 12px 0 32px rgba(40, 86, 126, 0.05);
  backdrop-filter: blur(18px);
  overflow-y: auto;
}

.nav-top {
  margin-bottom: 36px;
}

.back-button {
  height: 42px;
  border: none;
  border-radius: 10px;
  color: #102543;
  background: #fff;
  box-shadow: 0 8px 22px rgba(42, 91, 130, 0.08);
  font-weight: 800;
}

.side-nav :deep(.ant-menu) {
  border-inline-end: 0;
  background: transparent;
}

.side-nav :deep(.ant-menu-item),
.side-nav :deep(.ant-menu-submenu-title) {
  height: 50px;
  margin: 8px 0;
  border-radius: 10px;
  color: #233653;
  font-weight: 800;
}

.side-nav :deep(.ant-menu-item-selected) {
  color: #0b8b91;
  background: #e9fbfb;
}

.side-nav small {
  float: right;
  color: #8a98aa;
}

.nav-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  margin-left: 8px;
  color: #fff;
  background: #ff4d5a;
  font-size: 11px;
}

.nav-tip {
  margin-top: 72px;
  padding: 16px;
  border-radius: 12px;
  background: linear-gradient(135deg, #effaff, #e8f5ff);
  color: #4a607a;
  font-size: 13px;
  line-height: 1.6;
}

.nav-tip strong {
  display: block;
  margin-bottom: 6px;
  color: #1687d9;
}

.main-content {
  width: min(100%, 1280px);
  margin: 0 auto;
  padding: 42px 36px 56px;
}

.result-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 24px;
}

.title-line {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
}

.title-line h1 {
  margin: 0;
  font-size: 34px;
  line-height: 1.18;
  letter-spacing: 0;
  color: #071f42;
}

.saved-pill {
  height: 28px;
  display: inline-flex;
  align-items: center;
  padding: 0 12px;
  border-radius: 8px;
  color: #0f9a6b;
  background: #e8fbf2;
  font-weight: 800;
  font-size: 13px;
}

.meta-line {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  margin-top: 10px;
  color: var(--muted);
  font-size: 14px;
}

.header-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.ghost-action,
.primary-action,
.export-action {
  height: 42px;
  border-radius: 9px;
  font-weight: 800;
}

.ghost-action {
  border-color: var(--primary);
  color: #07848c;
  background: #fff;
}

.primary-action,
.export-action {
  border: none;
  background: linear-gradient(135deg, var(--primary), var(--accent));
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 22px;
  margin-bottom: 22px;
}

.metric-card,
.overview-card,
.recommend-section,
.info-card,
.daily-section,
.budget-section,
.diagnostics-section {
  border-radius: 12px;
  background: var(--surface);
  box-shadow: 0 14px 36px rgba(35, 82, 124, 0.09);
  border: 1px solid rgba(219, 234, 244, 0.86);
}

.metric-card {
  position: relative;
  min-height: 144px;
  padding: 24px;
  overflow: hidden;
}

.metric-label {
  display: block;
  color: #50617b;
  font-weight: 800;
  margin-bottom: 12px;
}

.metric-card strong {
  display: block;
  color: #08254b;
  font-size: 32px;
  line-height: 1;
}

.metric-card small {
  font-size: 15px;
  color: #4d5e77;
}

.metric-foot {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  margin-top: 14px;
  color: #68778f;
  font-size: 13px;
}

.metric-card :deep(.ant-progress) {
  margin-top: 8px;
}

.metric-card :deep(.ant-progress-bg) {
  background: linear-gradient(90deg, var(--primary), var(--accent));
}

.metric-blob {
  position: absolute;
  right: 22px;
  bottom: 22px;
  width: 52px;
  height: 52px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 900;
  opacity: 0.95;
}

.metric-blob.green {
  color: #29b36c;
  background: #e8f9ef;
}

.metric-blob.orange {
  color: #ff7043;
  background: #fff0e8;
}

.metric-blob.sky {
  color: #1687d9;
  background: #eaf5ff;
}

.weather-emoji {
  font-size: 28px;
}

.overview-card {
  display: grid;
  grid-template-columns: 1fr 1.18fr;
  gap: 26px;
  padding: 26px;
  margin-bottom: 22px;
}

.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  margin-bottom: 20px;
}

.panel-head h2 {
  margin: 0;
  color: #071f42;
  font-size: 22px;
}

.panel-head span {
  color: #68778f;
  font-weight: 700;
}

.timeline-list {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.timeline-list::before {
  content: '';
  position: absolute;
  left: 8px;
  top: 8px;
  bottom: 8px;
  width: 1px;
  background: linear-gradient(180deg, var(--primary), #a8dee7);
}

.timeline-row {
  display: grid;
  grid-template-columns: 18px 62px minmax(0, 1fr) 96px;
  align-items: center;
  gap: 14px;
}

.timeline-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--primary);
  border: 2px solid #e9fbfb;
  position: relative;
  z-index: 1;
}

.timeline-row time {
  color: #0e2a4d;
  font-weight: 800;
  font-size: 14px;
}

.timeline-copy strong {
  display: block;
  color: #0f2342;
  margin-bottom: 5px;
}

.timeline-copy span,
.timeline-copy small {
  display: block;
  color: #68778f;
  font-size: 12px;
  line-height: 1.45;
}

.timeline-row img {
  width: 96px;
  height: 64px;
  border-radius: 6px;
  object-fit: cover;
}

.next-day-button {
  width: 100%;
  border-radius: 7px;
  color: #0b8b91;
  font-weight: 800;
}

.timeline-day-actions {
  display: grid;
  gap: 10px;
  margin-top: 20px;
}

.map-panel {
  min-width: 0;
}

.map-tabs {
  display: inline-flex;
  padding: 4px;
  border-radius: 12px;
  background: #f2f8fb;
}

.map-tabs span {
  padding: 6px 14px;
  border-radius: 9px;
  color: #40536e;
  font-size: 13px;
}

.map-tabs span:first-child {
  color: #07848c;
  background: #e9fbfb;
}

#amap-container {
  width: 100%;
  height: 444px;
  overflow: hidden;
  border-radius: 10px;
  background: #edf6fb;
}

.recommend-section,
.daily-section,
.budget-section,
.diagnostics-section {
  padding: 22px;
  margin-bottom: 22px;
}

.section-title {
  margin-bottom: 16px;
  color: #102543;
  font-size: 18px;
  font-weight: 900;
}

.section-title small {
  color: #8493a6;
  font-weight: 700;
}

.recommend-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 18px;
}

.recommend-card {
  position: relative;
  min-height: 106px;
  padding: 18px;
  border-radius: 10px;
  overflow: hidden;
}

.recommend-card strong,
.recommend-card span,
.recommend-card small {
  display: block;
}

.recommend-card strong {
  margin-bottom: 10px;
  font-size: 17px;
}

.recommend-card span {
  color: #334661;
  font-weight: 800;
}

.recommend-card small {
  color: #6c7a90;
  margin-top: 6px;
}

.recommend-card b {
  position: absolute;
  right: 24px;
  bottom: 18px;
  font-size: 42px;
  opacity: 0.6;
}

.recommend-card.blue {
  color: #1687d9;
  background: #edf7ff;
}

.recommend-card.purple {
  color: #8e62d9;
  background: #f5efff;
}

.recommend-card.orange {
  color: #f47b33;
  background: #fff4ea;
}

.recommend-card.pink {
  color: #ec5a88;
  background: #fff0f5;
}

.bottom-grid {
  display: grid;
  grid-template-columns: 1.6fr 0.72fr 0.9fr;
  gap: 18px;
  margin-bottom: 22px;
}

.info-card {
  min-height: 140px;
  padding: 20px;
}

.risk-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.risk-row {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  color: #344761;
}

.weather-card strong {
  display: block;
  color: #071f42;
  font-size: 28px;
  margin-bottom: 8px;
}

.weather-card span,
.weather-card small,
.agent-card span,
.agent-card small {
  display: block;
  color: #64748b;
}

.agent-card {
  position: relative;
}

.agent-card .ant-btn {
  position: absolute;
  right: 18px;
  bottom: 18px;
}

.edit-alert {
  margin-bottom: 16px;
}

.day-header {
  display: grid;
  grid-template-columns: auto auto 1fr;
  gap: 14px;
  align-items: center;
  width: 100%;
}

.day-header span,
.day-header small {
  color: #78879b;
}

.day-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  padding: 14px;
  margin-bottom: 16px;
  border-radius: 10px;
  color: #40536e;
  background: #f6fbfe;
}

.attraction-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.attraction-card {
  display: grid;
  grid-template-columns: 132px minmax(0, 1fr);
  gap: 14px;
  padding: 14px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: #fff;
}

.attraction-card img {
  width: 132px;
  height: 112px;
  border-radius: 8px;
  object-fit: cover;
}

.attraction-title {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 8px;
}

.attraction-title strong {
  color: #102543;
}

.attraction-title span {
  color: #ff7043;
  font-weight: 900;
}

.attraction-card p {
  margin: 0 0 8px;
  color: #4d5e77;
  font-size: 13px;
  line-height: 1.55;
}

.attraction-card small {
  color: #7a899d;
  line-height: 1.45;
}

.edit-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.meal-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-top: 16px;
}

.meal-grid article {
  padding: 14px;
  border-radius: 10px;
  background: #fff9f2;
}

.meal-grid strong,
.meal-grid span,
.meal-grid small {
  display: block;
}

.meal-grid span,
.meal-grid small {
  color: #67758d;
  margin-top: 6px;
}

.budget-detail-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 14px;
}

.budget-detail-card {
  padding: 16px;
  border-radius: 10px;
  background: #f6fbfe;
}

.budget-detail-card span,
.budget-detail-card strong {
  display: block;
}

.budget-detail-card span {
  color: #68778f;
  margin-bottom: 8px;
}

.budget-detail-card strong {
  font-size: 22px;
  color: #1687d9;
}

.budget-detail-card.total {
  background: linear-gradient(135deg, #e9fbfb, #eef8ff);
}

.diagnostics-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}

.diagnostics-alert {
  margin-bottom: 16px;
}

.empty-state {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.empty-icon {
  font-size: 72px;
  color: #9bb3c8;
}

.back-top-button {
  width: 46px;
  height: 46px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  background: linear-gradient(135deg, var(--primary), var(--accent));
  box-shadow: 0 10px 26px rgba(28, 126, 180, 0.25);
  font-weight: 900;
}

:deep(.ant-collapse) {
  border: none;
  background: transparent;
}

:deep(.ant-collapse-item) {
  margin-bottom: 14px;
  border: 1px solid var(--line) !important;
  border-radius: 10px !important;
  overflow: hidden;
  background: #fff;
}

:deep(.ant-collapse-header) {
  align-items: center !important;
  padding: 16px 18px !important;
  background: #fbfdff;
}

:deep(.ant-collapse-content) {
  border-top: 1px solid var(--line);
}

:deep(.ant-collapse-content-box) {
  padding: 18px;
}

@media (max-width: 1180px) {
  .workspace {
    grid-template-columns: 1fr;
  }

  .side-nav {
    position: static;
    height: auto;
    padding: 16px;
  }

  .nav-top,
  .nav-tip {
    display: none;
  }

  .side-nav :deep(.ant-menu) {
    display: flex;
    overflow-x: auto;
    white-space: nowrap;
  }

  .side-nav :deep(.ant-menu-submenu) {
    flex: 0 0 auto;
  }

  .main-content {
    padding: 28px 20px 44px;
  }

  .metric-grid,
  .recommend-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .overview-card,
  .bottom-grid {
    grid-template-columns: 1fr;
  }

  .budget-detail-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 720px) {
  .main-content {
    padding: 22px 12px 36px;
  }

  .result-header {
    flex-direction: column;
  }

  .title-line h1 {
    font-size: 26px;
  }

  .header-actions {
    width: 100%;
    justify-content: flex-start;
  }

  .metric-grid,
  .recommend-grid,
  .attraction-grid,
  .meal-grid,
  .budget-detail-grid {
    grid-template-columns: 1fr;
  }

  .overview-card {
    padding: 18px;
  }

  .timeline-row {
    grid-template-columns: 18px 54px minmax(0, 1fr);
  }

  .timeline-row img {
    display: none;
  }

  #amap-container {
    height: 300px;
  }

  .attraction-card {
    grid-template-columns: 1fr;
  }

  .attraction-card img {
    width: 100%;
    height: 170px;
  }
}
</style>
