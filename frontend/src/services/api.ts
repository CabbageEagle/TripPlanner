import axios from 'axios'
import type { TripFormData, TripPlan, TripPlanResponse, TripPlanUpdateRequest } from '@/types'

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

export interface TripPlanStreamEvent {
  event: 'progress' | 'done' | 'error'
  data: any
}

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 300000,
  headers: {
    'Content-Type': 'application/json'
  }
})

apiClient.interceptors.request.use(
  (config) => {
    console.log('发送请求:', config.method?.toUpperCase(), config.url)
    return config
  },
  (error) => {
    console.error('请求错误:', error)
    return Promise.reject(error)
  }
)

apiClient.interceptors.response.use(
  (response) => {
    console.log('收到响应:', response.status, response.config.url)
    return response
  },
  (error) => {
    console.error('响应错误:', error.response?.status, error.message)
    return Promise.reject(error)
  }
)

export async function generateTripPlan(formData: TripFormData): Promise<TripPlanResponse> {
  try {
    const response = await apiClient.post<TripPlanResponse>('/api/trip/plan', formData)
    return response.data
  } catch (error: any) {
    console.error('生成旅行计划失败:', error)
    throw new Error(error.response?.data?.detail || error.message || '生成旅行计划失败')
  }
}

function parseSSEBlock(block: string): TripPlanStreamEvent | null {
  const lines = block.split(/\r?\n/)
  let eventName: TripPlanStreamEvent['event'] = 'progress'
  const dataLines: string[] = []

  for (const line of lines) {
    if (line.startsWith('event:')) {
      const name = line.slice(6).trim()
      if (name === 'progress' || name === 'done' || name === 'error') {
        eventName = name
      }
      continue
    }
    if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trim())
    }
  }

  if (!dataLines.length) {
    return null
  }

  const dataText = dataLines.join('\n')
  let payload: any = {}
  try {
    payload = JSON.parse(dataText)
  } catch {
    payload = { message: dataText }
  }

  return { event: eventName, data: payload }
}

export async function generateTripPlanStream(
  formData: TripFormData,
  onEvent?: (event: TripPlanStreamEvent) => void
): Promise<TripPlanResponse> {
  const response = await fetch(`${API_BASE_URL}/api/trip/plan/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(formData)
  })

  if (!response.ok) {
    let detail = `HTTP ${response.status}`
    try {
      const body = await response.json()
      detail = body?.detail || detail
    } catch {
      // noop
    }
    throw new Error(detail)
  }

  if (!response.body) {
    throw new Error('流式响应体为空')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  let finalResponse: TripPlanResponse | null = null

  while (true) {
    const { done, value } = await reader.read()
    if (done) {
      break
    }

    buffer += decoder.decode(value, { stream: true })

    let separatorIndex = buffer.indexOf('\n\n')
    while (separatorIndex !== -1) {
      const rawBlock = buffer.slice(0, separatorIndex).trim()
      buffer = buffer.slice(separatorIndex + 2)

      if (rawBlock) {
        const parsed = parseSSEBlock(rawBlock)
        if (parsed) {
          onEvent?.(parsed)
          if (parsed.event === 'done') {
            finalResponse = parsed.data as TripPlanResponse
          } else if (parsed.event === 'error') {
            throw new Error(parsed.data?.message || '生成旅行计划失败')
          }
        }
      }

      separatorIndex = buffer.indexOf('\n\n')
    }
  }

  buffer += decoder.decode()
  const remaining = buffer.trim()
  if (remaining) {
    const parsed = parseSSEBlock(remaining)
    if (parsed) {
      onEvent?.(parsed)
      if (parsed.event === 'done') {
        finalResponse = parsed.data as TripPlanResponse
      } else if (parsed.event === 'error') {
        throw new Error(parsed.data?.message || '生成旅行计划失败')
      }
    }
  }

  if (finalResponse) {
    return finalResponse
  }
  throw new Error('流式响应提前结束，未返回最终结果')
}

export async function getTripPlan(planId: string): Promise<TripPlanResponse> {
  try {
    const response = await apiClient.get<TripPlanResponse>(`/api/trip/plans/${planId}`)
    return response.data
  } catch (error: any) {
    console.error('获取旅行计划失败:', error)
    throw new Error(error.response?.data?.detail || error.message || '获取旅行计划失败')
  }
}

export async function updateTripPlan(planId: string, tripPlan: TripPlan, note?: string): Promise<TripPlanResponse> {
  try {
    const payload: TripPlanUpdateRequest = {
      data: tripPlan,
      note
    }
    const response = await apiClient.put<TripPlanResponse>(`/api/trip/plans/${planId}`, payload)
    return response.data
  } catch (error: any) {
    console.error('保存旅行计划失败:', error)
    throw new Error(error.response?.data?.detail || error.message || '保存旅行计划失败')
  }
}

export async function healthCheck(): Promise<any> {
  try {
    const response = await apiClient.get('/health')
    return response.data
  } catch (error: any) {
    console.error('健康检查失败:', error)
    throw new Error(error.message || '健康检查失败')
  }
}

export default apiClient
