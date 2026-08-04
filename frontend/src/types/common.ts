/**
 * 通用类型定义。
 */

/** 媒体类型 */
export type MediaType = 'movie' | 'tv'

/** 通用操作结果（success + message） */
export interface ActionResponse {
  success: boolean
  message: string
}
