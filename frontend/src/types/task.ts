/**
 * 定时任务相关类型 — 镜像 backend/app/routers/tasks.py。
 */

/** 自动补缺进度 */
export interface AutoFillProgress {
  current: number
  total: number
  [key: string]: unknown
}

/** 定时任务状态响应 */
export interface TaskStatus {
  running: boolean
  last_run: string | null
  last_result: Record<string, unknown> | null
  config: TaskConfig
  auto_fill_cursor: number | null
  auto_fill_last_run: string | null
  auto_fill_progress: AutoFillProgress | null
}

/** 定时任务配置 */
export interface TaskConfig {
  interval: number
  auto_fill_enabled: boolean
  auto_fill_interval_seconds: number
  mp_supplement_enabled?: boolean
  [key: string]: unknown
}

/** 更新定时任务配置请求 */
export interface TaskConfigUpdate {
  interval?: number
  auto_fill_enabled?: boolean
  auto_fill_interval_seconds?: number
  mp_supplement_enabled?: boolean
}

/** 手动触发任务响应 */
export interface TaskTriggerResponse {
  success: boolean
  message: string
  sync_count: number
  mp_search_count: number
}
