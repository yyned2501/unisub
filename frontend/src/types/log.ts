/**
 * 日志查看相关类型 — 镜像 backend/app/routers/logs.py。
 */

/** 日志文件信息 */
export interface LogFileInfo {
  name: string
  size: number
  mtime: number
}

/** 日志文件列表响应 */
export interface LogFilesResponse {
  files: LogFileInfo[]
}

/** 日志内容查询参数 */
export interface LogContentParams {
  lines?: number
  filter?: string
  level?: string
  tail?: boolean
}

/** 日志内容响应 */
export interface LogContentResponse {
  file: string
  total_lines: number
  lines: string[]
}

/** Debug 信息响应 */
export interface DebugInfo {
  debug: boolean
  database_url: string
  cors_origins: string[]
  log_dir: string
  log_dir_exists: boolean
  log_files: string[]
}
