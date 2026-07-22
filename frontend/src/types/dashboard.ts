/**
 * 看板相关类型 — 镜像 backend/app/schemas/dashboard.py。
 */

/** 看板统计数据 */
export interface DashboardStats {
  total_subscriptions: number
  movie_count: number
  tv_count: number
  missing_count: number
  completed_count: number
  tmdb_cached_total: number
  tmdb_data_filled: number
}

/** 单个平台连接状态 */
export interface PlatformStatus {
  name: string
  enabled: boolean
  connected: boolean
  message: string
}

/** 活动日志响应体 */
export interface ActivityLog {
  id: string
  action: string
  tmdb_id: number | null
  message: string
  created_at: string
}

/** NextFind 额度/积分信息 */
export interface NextFindQuota {
  quota?: {
    status?: string
    data?: Record<string, string>
  } | null
  error?: string | null
}
