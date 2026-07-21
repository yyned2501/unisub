/**
 * 平台配置相关类型 — 镜像 backend/app/schemas/platform.py。
 */

/** 创建平台配置请求体 */
export interface PlatformConfigCreate {
  name: string
  base_url: string
  api_key: string
  enabled?: boolean
}

/** 更新平台配置请求体（字段可选，仅更新传入项） */
export interface PlatformConfigUpdate {
  name?: string
  base_url?: string
  api_key?: string
  enabled?: boolean
}

/** 平台配置响应体（api_key 已脱敏） */
export interface PlatformConfig {
  id: string
  name: string
  base_url: string
  api_key: string
  enabled: boolean
  created_at: string
  updated_at: string
}

/** 平台连接测试结果 */
export interface PlatformTestResult {
  success: boolean
  message: string
  details?: Record<string, unknown> | null
}
