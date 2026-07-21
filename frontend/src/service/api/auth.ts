import apiClient from '../request'
import type { LoginResponse, AuthInfo } from '@/types'

export function login(username: string, password: string) {
  const formData = new URLSearchParams()
  formData.append('username', username)
  formData.append('password', password)
  return apiClient.post<LoginResponse>('/v1/login/access-token', formData, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  })
}

export function getAuthInfo() {
  return apiClient.get<AuthInfo>('/v1/auth/info')
}

export function updateAuth(username: string, password: string) {
  return apiClient.put<{ success: boolean; message?: string }>('/v1/auth/update', { username, password })
}
