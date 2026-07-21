/**
 * 搜索相关类型 — 镜像 backend/app/schemas/search.py。
 */
import type { MediaType } from './common'

/** 搜索结果中的单个媒体条目 */
export interface SearchResultItem {
  tmdb_id: number
  title: string
  media_type: MediaType
  year: number | null
  poster_url: string | null
  overview: string | null
  is_subscribed: boolean
}

/** 搜索响应体 */
export interface SearchResponse {
  total: number
  items: SearchResultItem[]
}
