import apiClient from '../request'

export function login(username, password) {
  const formData = new URLSearchParams()
  formData.append('username', username)
  formData.append('password', password)
  return apiClient.post('/v1/login/access-token', formData, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  })
}

export function getAuthInfo() {
  return apiClient.get('/v1/auth/info')
}

export function updateAuth(username, password) {
  return apiClient.put('/v1/auth/update', { username, password })
}