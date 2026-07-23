import apiClient from '../request'
import type {
  EmbyMissingAnalysis,
  EmbySyncResult,
  EmbyBlacklistEntry,
  EmbyScanStatus,
  Tmdb404Item,
  Tmdb404ResolveResult,
  ActionResponse,
  MediaType,
} from '@/types'

export function getEmbyLibraryAnalysis(params: { page?: number; page_size?: number; library?: string } = {}) {
  return apiClient.get<EmbyMissingAnalysis>('/emby/library-analysis', { params })
}

export function syncEmbyCache() {
  return apiClient.post<EmbySyncResult>('/emby/sync-cache')
}

export function backfillOverview() {
  return apiClient.post<{ success: boolean; checked: number; filled: number; message: string }>(
    '/emby/backfill-overview'
  )
}

export function updateEmbyTmdb() {
  return apiClient.post<ActionResponse>('/emby/update-tmdb')
}

export function getBlacklist() {
  return apiClient.get<EmbyBlacklistEntry[]>('/emby/blacklist')
}

export function addToBlacklist(tmdbId: number) {
  return apiClient.post<ActionResponse>('/emby/blacklist', { tmdb_id: tmdbId })
}

export function removeFromBlacklist(tmdbId: number) {
  return apiClient.delete<ActionResponse>(`/emby/blacklist/${tmdbId}`)
}

export function triggerEmbyScan() {
  return apiClient.post<ActionResponse>('/emby/scan')
}

export function getEmbyScanStatus() {
  return apiClient.get<EmbyScanStatus>('/emby/scan-status')
}

export function subscribeFromEmby(
  tmdbId: number,
  title: string,
  mediaType: MediaType = 'tv',
  posterUrl: string | null = null,
  year: number | null = null
) {
  return apiClient.post<ActionResponse>('/emby/subscribe', {
    tmdb_id: tmdbId,
    title,
    media_type: mediaType,
    poster_url: posterUrl,
    year,
  })
}

export function deleteEmbyItem(tmdbId: number) {
  return apiClient.delete<ActionResponse>(`/emby/item/${tmdbId}`)
}

export function getTmdb404List() {
  return apiClient.get<Tmdb404Item[]>('/emby/tmdb-404')
}

export function moveTmdb404Item(tmdbId: number) {
  return apiClient.post<ActionResponse>(`/emby/tmdb-404/${tmdbId}/move`)
}

export function resolveTmdb404Path(tmdbId: number) {
  return apiClient.post<Tmdb404ResolveResult>(`/emby/tmdb-404/${tmdbId}/resolve`)
}
