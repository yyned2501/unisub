import apiClient from './index'

/** 获取所有平台配置 */
export function getPlatforms() {
  return apiClient.get('/platforms')
}

/** 添加平台配置 */
export function createPlatform(data) {
  return apiClient.post('/platforms', data)
}

/** 更新平台配置 */
export function updatePlatform(id, data) {
  return apiClient.put(`/platforms/${id}`, data)
}

/** 删除平台配置 */
export function deletePlatform(id) {
  return apiClient.delete(`/platforms/${id}`)
}

/** 测试平台连接 */
export function testPlatform(id) {
  return apiClient.post(`/platforms/${id}/test`)
}
