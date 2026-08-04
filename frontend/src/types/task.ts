/**
 * 定时任务相关类型 — 镜像 backend/app/schemas/task.py。
 */

/** 定时任务配置 — 对应后端 _task_config */
export interface TaskConfig {
  interval_minutes: number
  light_interval_minutes: number
  sync_interval_minutes: number
  tmdb_interval_minutes: number
  mp_supplement_enabled: boolean
  auto_sync_enabled: boolean
}

/** 更新定时任务配置请求 */
export type TaskConfigUpdate = Partial<TaskConfig>

/** 定时任务状态响应 */
export interface TaskStatus {
  running: boolean
  last_run: string | null
  last_result: Record<string, unknown> | null
  config: TaskConfig
}
