import apiClient from '../request'
import type {
  AutoSubConfigResponse,
  AutoSubConfigUpdate,
  AutoSubRunResponse,
  AutoSubHistoryResponse,
  AutoSubMetaResponse,
} from '@/types'

export function getAutoSubConfig() {
  return apiClient.get<AutoSubConfigResponse>('/auto-subscribe/config')
}

export function updateAutoSubConfig(data: AutoSubConfigUpdate) {
  return apiClient.put<AutoSubConfigResponse>('/auto-subscribe/config', data)
}

export function triggerAutoSubRun() {
  return apiClient.post<AutoSubRunResponse>('/auto-subscribe/run')
}

export function getAutoSubHistory() {
  return apiClient.get<AutoSubHistoryResponse>('/auto-subscribe/history')
}

export function clearAutoSubHistory() {
  return apiClient.delete<void>('/auto-subscribe/history')
}

export function getAutoSubMeta() {
  return apiClient.get<AutoSubMetaResponse>('/auto-subscribe/meta')
}
