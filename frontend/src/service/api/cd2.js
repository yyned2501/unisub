import apiClient from '../request'

export function getCd2Config() {
  return apiClient.get('/settings/cd2')
}

export function updateCd2Config(data) {
  return apiClient.put('/settings/cd2', data)
}

export function testCd2Connection() {
  return apiClient.post('/settings/cd2/test')
}
