import axios from 'axios'
import type { TripFormData, TripPlan, TripPlanResponse, TripPlanUpdateRequest } from '@/types'

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

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
