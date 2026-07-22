import apiClient from '../request'
import type { Subscription, SubscriptionCreate, SubscriptionSyncResult } from '@/types'

export function getSubscriptions(params: Record<string, unknown> = {}) {
  return apiClient.get<Subscription[]>('/subscriptions', { params })
}

export function createSubscription(data: SubscriptionCreate) {
  return apiClient.post<Subscription>('/subscriptions', data)
}

export function deleteSubscription(id: string) {
  return apiClient.delete<void>(`/subscriptions/${id}`)
}

export function getSubscription(id: string) {
  return apiClient.get<Subscription>(`/subscriptions/${id}`)
}

export function syncSubscriptions() {
  return apiClient.post<SubscriptionSyncResult[]>('/subscriptions/sync')
}

export function toggleBlacklist(id: string) {
  return apiClient.patch<{ success: boolean; blacklisted: boolean; message: string }>(`/subscriptions/${id}/blacklist`)
}
