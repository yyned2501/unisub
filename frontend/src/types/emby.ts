/**
 * Emby 媒体库相关类型 — 镜像 backend/app/schemas/emby.py、emby_cache.py。
 */

/** Emby 缓存剧集（含 adjusted_missing 计算字段） */
export interface EmbyCacheResponse {
  tmdb_id: number
  emby_series_name: string | null
  emby_year: number | null
  emby_episode_count: number | null
  emby_image_url: string | null
  emby_path: string | null
  emby_library_name: string | null
  overview: string | null
  poster_url: string | null
  tmdb_total_eps: number | null
  tmdb_aired_eps: number | null
  tmdb_next_air_date: string | null
  is_subscribed: boolean
  is_blacklisted: boolean
  adjusted_missing: number | null
}

/** 缺集分析结果（分页） */
export interface EmbyMissingAnalysis {
  total_series: number
  subscribed_count: number
  missing_count: number
  series: EmbyCacheResponse[]
  page: number
  page_size: number
  total_pages: number
  /** 所有 Emby 媒体库名称列表 */
  libraries: string[]
}

/** TMDB 404 条目 — EmbyCache 有但 TmdbCache 无对应记录 */
export interface Tmdb404Item {
  tmdb_id: number
  emby_series_name: string | null
  emby_year: number | null
  emby_path: string | null
  cd2_path: string | null
  emby_image_url: string | null
  detected_at: string | null
}

/** Emby 同步操作结果 */
export interface EmbySyncResult {
  success: boolean
  total_synced: number
  message: string
}

/** 全量扫描进度状态 */
export interface EmbyScanStatus {
  running: boolean
  progress: number
  current_step: number
  total_steps: number
  step_name: string
  total_items: number
  current_item: number
  started_at: string | null
  error: string | null
}

/** TMDB 404 路径确认结果 */
export interface Tmdb404ResolveResult {
  verified: boolean
  cd2_path: string
  name?: string
  file_type?: 'directory' | 'file'
  sub_items?: number
  sub_file_names?: string[]
  note?: string
}

/** 黑名单条目 */
export interface EmbyBlacklistEntry {
  tmdb_id: number
  created_at: string
}
