import apiClient from './index'

/** 获取订阅列表 */
export function getSubscriptions() {
  return apiClient.get('/subscriptions')
}

/** 添加订阅 */
export function createSubscription(data) {
  return apiClient.post('/subscriptions', data)
}

/** 删除订阅 */
export function deleteSubscription(id) {
  return apiClient.delete(`/subscriptions/${id}`)
}

/** 获取订阅详情 */
export function getSubscription(id) {
  return apiClient.get(`/subscriptions/${id}`)
}

/** 手动同步订阅状态 */
export function syncSubscriptions() {
  return apiClient.post('/subscriptions/sync')
}
