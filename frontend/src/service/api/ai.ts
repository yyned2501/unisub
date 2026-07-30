import apiClient from '../request'
import type {
  AiConfigResponse,
  AiConfigUpdate,
  AiModelListRequest,
  AiModelListResponse,
} from '@/types'

export function getAiConfig() {
  return apiClient.get<AiConfigResponse>('/ai/config')
}

export function updateAiConfig(data: AiConfigUpdate) {
  return apiClient.put<AiConfigResponse>('/ai/config', data)
}

export function fetchAIModels(data: AiModelListRequest) {
  return apiClient.post<AiModelListResponse>('/ai/models', data)
}
