import apiClient from '../request'
import type { PlatformConfig, PlatformConfigCreate, PlatformConfigUpdate, PlatformTestResult } from '@/types'

export function getPlatforms() {
  return apiClient.get<PlatformConfig[]>('/platforms')
}

export function createPlatform(data: PlatformConfigCreate) {
  return apiClient.post<PlatformConfig>('/platforms', data)
}

export function updatePlatform(id: string, data: PlatformConfigUpdate) {
  return apiClient.put<PlatformConfig>(`/platforms/${id}`, data)
}

export function deletePlatform(id: string) {
  return apiClient.delete<void>(`/platforms/${id}`)
}

export function testPlatform(id: string) {
  return apiClient.post<PlatformTestResult>(`/platforms/${id}/test`)
}
