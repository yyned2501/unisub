import apiClient from '../request'
import type { DashboardStats, PlatformStatus, ActivityLog, NextFindQuota } from '@/types'

export function getStats() {
  return apiClient.get<DashboardStats>('/dashboard/stats')
}

export function getPlatformStatus() {
  return apiClient.get<PlatformStatus[]>('/dashboard/platforms')
}

export function getActivities() {
  return apiClient.get<ActivityLog[]>('/dashboard/activities')
}

export function getNextFindQuota() {
  return apiClient.get<NextFindQuota>('/dashboard/nextfind-quota')
}