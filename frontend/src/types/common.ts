/**
 * 通用类型定义。
 */

/** 媒体类型 */
export type MediaType = 'movie' | 'tv'

/** 后端分页响应通用结构 */
export interface Paginated<T> {
  total: number
  page: number
  page_size: number
  total_pages: number
  items: T[]
}

/** 通用操作结果（success + message） */
export interface ActionResponse {
  success: boolean
  message: string
}
