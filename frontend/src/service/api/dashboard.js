import apiClient from '../request'

export function getStats() {
  return apiClient.get('/dashboard/stats')
}

export function getPlatformStatus() {
  return apiClient.get('/dashboard/platforms')
}

export function getActivities() {
  return apiClient.get('/dashboard/activities')
}

export function getNextFindQuota() {
  return apiClient.get('/dashboard/nextfind-quota')
}
