import apiClient from './index'

/** 搜索媒体 */
export function searchMedia(query, type = '') {
  const params = { q: query }
  if (type && type !== 'all') {
    params.type = type
  }
  return apiClient.get('/search', { params })
}
