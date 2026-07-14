import apiClient from '../request'

export function getPlatforms() {
  return apiClient.get('/platforms')
}

export function createPlatform(data) {
  return apiClient.post('/platforms', data)
}

export function updatePlatform(id, data) {
  return apiClient.put(`/platforms/${id}`, data)
}

export function deletePlatform(id) {
  return apiClient.delete(`/platforms/${id}`)
}

export function testPlatform(id) {
  return apiClient.post(`/platforms/${id}/test`)
}
