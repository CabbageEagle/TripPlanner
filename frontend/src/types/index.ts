// 类型定义

export interface Location {
  longitude: number
  latitude: number
}

export interface Attraction {
  name: string
  address: string
  location: Location
  visit_duration: number
  description: string
  category?: string
  rating?: number
  image_url?: string
  ticket_price?: number
}

export interface Meal {
  type: 'breakfast' | 'lunch' | 'dinner' | 'snack'
  name: string
  address?: string
  location?: Location
  description?: string
  estimated_cost?: number
}

export interface Hotel {
  name: string
  address: string
  location?: Location
  price_range: string
  rating: string
  distance: string
  type: string
  estimated_cost?: number
}

export interface Budget {
  total_attractions: number
  total_hotels: number
  total_meals: number
  total_transportation: number
  total: number
}

export interface DayPlan {
  date: string
  day_index: number
  description: string
  transportation: string
  accommodation: string
  hotel?: Hotel
  attractions: Attraction[]
  meals: Meal[]
  total_cost?: number
  total_duration?: number
  timeline?: TimelineItem[]
}

export interface WeatherInfo {
  date: string
  day_weather: string
  night_weather: string
  day_temp: number | string
  night_temp: number | string
  wind_direction: string
  wind_power: string
}

export interface TimelineItem {
  start_time: string
  end_time: string
  activity_type: string
  activity_name: string
  duration: number
  location?: Location
  cost?: number
}

export interface Conflict {
  conflict_type: 'time' | 'budget' | 'capacity' | string
  severity: 'critical' | 'warning' | 'info' | string
  description: string
  affected_items: string[]
  day_index?: number | null
}

export interface BudgetUsage {
  total_budget: number
  used_budget: number
  remaining_budget: number
  breakdown: Record<string, number>
  over_budget: boolean
  over_budget_amount: number
}

export interface TripPlan {
  city: string
  start_date: string
  end_date: string
  days: DayPlan[]
  weather_info: WeatherInfo[]
  overall_suggestions: string
  budget?: Budget
  budget_usage?: BudgetUsage
  time_conflicts?: Conflict[]
  warnings?: string[]
}

export interface TripFormData {
  city: string
  start_date: string
  end_date: string
  travel_days: number
  transportation: string
  accommodation: string
  preferences: string[]
  free_text_input: string
  // 预算字段
  max_budget?: number
  budget_per_day?: number
  // 时间字段
  daily_start_time?: string
  daily_end_time?: string
  max_attractions_per_day?: number
}

export interface TripPlanResponse {
  success: boolean
  message: string
  data?: TripPlan
}

