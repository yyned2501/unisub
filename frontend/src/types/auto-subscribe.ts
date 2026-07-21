/**
 * 自动订阅相关类型 — 镜像 backend/app/schemas/auto_subscribe.py。
 */

/** 自动订阅配置（前端维护的完整字段集） */
export interface AutoSubConfig {
  enabled: boolean
  min_year: number
  min_vote: number
  media_type: string
  schedule_cron: string
  douban_enabled: boolean
  douban_ranks: string[]
  douban_rsshub: string
  douban_rss_custom: string
  mikan_enabled: boolean
  mikan_season: string
  mikan_year: number
  mikan_resolve_detail: boolean
  maoyan_enabled: boolean
  maoyan_movie_box: boolean
  maoyan_web_platforms: string[]
  maoyan_web_types: string[]
  maoyan_num: number
  proxy_url: string
  [key: string]: unknown
}

/** 自动订阅配置响应 */
export interface AutoSubConfigResponse {
  config: Partial<AutoSubConfig>
  last_run: string | null
  last_stats: Record<string, unknown> | null
  enabled_sources: string[]
  status_labels: Record<string, string>
  source_names: Record<string, string>
  running: boolean
  last_error: string | null
}

/** 自动订阅配置更新请求 */
export interface AutoSubConfigUpdate {
  config: Partial<AutoSubConfig>
}

/** 手动触发运行响应 */
export interface AutoSubRunResponse {
  success: boolean
  started: boolean
  message: string
}

/** 单条自动订阅历史记录 */
export interface AutoSubHistoryItem {
  key: string
  status: string
  time: string | null
  tmdb_id: number | null
  media_type: string | null
}

/** 自动订阅历史响应 */
export interface AutoSubHistoryResponse {
  items: AutoSubHistoryItem[]
  last_run: string | null
  stats: Record<string, unknown> | null
}

/** 下拉选项 */
export interface SelectOption {
  value: string
  label: string
}

/** 自动订阅元数据响应（供前端下拉选项） */
export interface AutoSubMetaResponse {
  douban_ranks: SelectOption[]
  maoyan_platforms: SelectOption[]
  maoyan_media_types: SelectOption[]
  seasons: SelectOption[]
  source_names: Record<string, string>
  status_labels: Record<string, string>
}
