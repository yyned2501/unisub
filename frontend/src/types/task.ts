/**
 * 定时任务相关类型 — 镜像 backend/app/routers/tasks.py。
 */

/** 定时任务状态响应 */
export interface TaskStatus {
  running: boolean
  last_run: string | null
  last_result: Record<string, unknown> | null
  config: TaskConfig
}

/** 定时任务配置 */
export interface TaskConfig {
  interval: number
  mp_supplement_enabled?: boolean
  [key: string]: unknown
}

/** 更新定时任务配置请求 */
export interface TaskConfigUpdate {
  interval?: number
  mp_supplement_enabled?: boolean
}

/** 手动触发任务响应 */
export interface TaskTriggerResponse {
  success: boolean
  message: string
  sync_count: number
  mp_search_count: number
}
