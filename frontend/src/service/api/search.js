import apiClient from '../request'

/**
 * 搜索媒体
 * @param {string} query 关键词
 * @param {'all'|'movie'|'tv'} type 类型筛选
 */
export function searchMedia(query, type = 'all') {
  const params = { q: query }
  if (type && type !== 'all') {
    params.type = type
  }
  return apiClient.get('/search', { params })
}
