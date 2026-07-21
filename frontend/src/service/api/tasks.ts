import apiClient from '../request'
import type { TaskStatus, TaskTriggerResponse, TaskConfigUpdate, TaskConfig } from '@/types'

export function getTaskStatus() {
  return apiClient.get<TaskStatus>('/tasks/status')
}

export function triggerTask() {
  return apiClient.post<TaskTriggerResponse>('/tasks/trigger')
}

export function updateTaskConfig(data: TaskConfigUpdate) {
  return apiClient.put<{ success: boolean; config: TaskConfig }>('/tasks/config', data)
}