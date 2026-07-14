import apiClient from '../request'

export function getTaskStatus() {
  return apiClient.get('/tasks/status')
}

export function triggerTask() {
  return apiClient.post('/tasks/trigger')
}

export function updateTaskConfig(data) {
  return apiClient.put('/tasks/config', data)
}
