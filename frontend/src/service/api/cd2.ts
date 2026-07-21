import apiClient from '../request'
import type { Cd2Config, Cd2ConfigUpdate, Cd2TestResult } from '@/types'

export function getCd2Config() {
  return apiClient.get<Cd2Config>('/settings/cd2')
}

export function updateCd2Config(data: Cd2ConfigUpdate) {
  return apiClient.put<Cd2Config>('/settings/cd2', data)
}

export function testCd2Connection() {
  return apiClient.post<Cd2TestResult>('/settings/cd2/test')
}
