/**
 * 订阅相关类型 — 镜像 backend/app/schemas/subscription.py。
 */
import type { MediaType } from './common'

/** 创建订阅请求体 */
export interface SubscriptionCreate {
  tmdb_id: number
  media_type: MediaType
  title: string
  poster_url?: string | null
  year?: number | null
  source?: string | null
}

/** 订阅记录响应体 */
export interface Subscription {
  id: string
  tmdb_id: number
  media_type: MediaType
  title: string
  poster_url: string | null
  year: number | null
  nf_subscribed: boolean
  nf_status: string | null
  nf_missing_eps: number
  nf_sub_id: string | null
  completed: boolean
  aired_complete: boolean
  source: string | null
  created_at: string
  updated_at: string
  adjusted_missing_eps: number | null
  tmdb_aired_eps: number | null
}

/** 单条订阅同步结果 */
export interface SubscriptionSyncResult {
  tmdb_id: number
  title: string
  /** created / pushed_to_nf / updated / skipped */
  action: string
  nf_status: string | null
  nf_missing_eps: number
  nf_subscribed: boolean
  needs_mp_search: boolean
  message: string
}
