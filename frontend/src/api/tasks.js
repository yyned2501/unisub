import apiClient from './index'

/** 获取定时任务状态 */
export function getTaskStatus() {
  return apiClient.get('/tasks/status')
}

/** 手动触发一次编排 */
export function triggerTask() {
  return apiClient.post('/tasks/trigger')
}

/** 更新定时任务配置 */
export function updateTaskConfig(data) {
  return apiClient.put('/tasks/config', data)
}
