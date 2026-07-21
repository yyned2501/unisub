import apiClient from '../request'

export function getAutoSubConfig() {
  return apiClient.get('/auto-subscribe/config')
}

export function updateAutoSubConfig(data) {
  return apiClient.put('/auto-subscribe/config', data)
}

export function triggerAutoSubRun() {
  return apiClient.post('/auto-subscribe/run')
}

export function getAutoSubHistory() {
  return apiClient.get('/auto-subscribe/history')
}

export function clearAutoSubHistory() {
  return apiClient.delete('/auto-subscribe/history')
}

export function getAutoSubMeta() {
  return apiClient.get('/auto-subscribe/meta')
}