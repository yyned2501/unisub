import apiClient from './index'

/** 获取订阅统计 */
export function getStats() {
  return apiClient.get('/dashboard/stats')
}

/** 获取平台状态 */
export function getPlatformStatus() {
  return apiClient.get('/dashboard/platforms')
}

/** 获取最近活动 */
export function getActivities() {
  return apiClient.get('/dashboard/activities')
}

/** 获取 NextFind 额度 */
export function getNextFindQuota() {
  return apiClient.get('/dashboard/nextfind-quota')
}
