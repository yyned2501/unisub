import apiClient from '../request'

export function getSubscriptions(params = {}) {
  return apiClient.get('/subscriptions', { params })
}

export function createSubscription(data) {
  return apiClient.post('/subscriptions', data)
}

export function deleteSubscription(id) {
  return apiClient.delete(`/subscriptions/${id}`)
}

export function getSubscription(id) {
  return apiClient.get(`/subscriptions/${id}`)
}

export function syncSubscriptions() {
  return apiClient.post('/subscriptions/sync')
}
