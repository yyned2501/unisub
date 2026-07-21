/**
 * CloudDrive2 配置相关类型 — 镜像 backend/app/schemas/cd2.py。
 */

/** 更新 CloudDrive2 配置请求体 */
export interface Cd2ConfigUpdate {
  base_url: string
  api_key: string
  target_path: string
  path_prefix?: string
  path_replacement?: string
  enabled?: boolean
}

/** CloudDrive2 配置响应体（api_key 已脱敏） */
export interface Cd2Config {
  id: string
  base_url: string
  api_key: string
  target_path: string
  path_prefix: string
  path_replacement: string
  enabled: boolean
  created_at: string
  updated_at: string
}

/** CloudDrive2 连接测试结果 */
export interface Cd2TestResult {
  success: boolean
  message: string
  details?: Record<string, string | boolean> | null
}
