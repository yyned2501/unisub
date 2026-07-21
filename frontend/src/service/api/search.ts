import apiClient from '../request'
import type { SearchResponse, MediaType } from '@/types'

/**
 * 搜索媒体
 * @param query 关键词
 * @param type 类型筛选
 */
export function searchMedia(query: string, type: MediaType | 'all' = 'all') {
  const params: { q: string; type?: string } = { q: query }
  if (type && type !== 'all') {
    params.type = type
  }
  return apiClient.get<SearchResponse>('/search', { params })
}
