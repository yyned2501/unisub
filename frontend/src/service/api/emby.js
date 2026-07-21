import apiClient from '../request'

export function getEmbyLibraryAnalysis(params = {}) {
  return apiClient.get('/emby/library-analysis', { params })
}

export function syncEmbyCache() {
  return apiClient.post('/emby/sync-cache')
}

export function updateEmbyTmdb() {
  return apiClient.post('/emby/update-tmdb')
}

export function getBlacklist() {
  return apiClient.get('/emby/blacklist')
}

export function addToBlacklist(tmdbId) {
  return apiClient.post('/emby/blacklist', { tmdb_id: tmdbId })
}

export function removeFromBlacklist(tmdbId) {
  return apiClient.delete(`/emby/blacklist/${tmdbId}`)
}

export function triggerEmbyScan() {
  return apiClient.post('/emby/scan')
}

export function getEmbyScanStatus() {
  return apiClient.get('/emby/scan-status')
}

export function subscribeFromEmby(tmdbId, title, mediaType = 'tv', posterUrl = null, year = null) {
  return apiClient.post('/emby/subscribe', { tmdb_id: tmdbId, title, media_type: mediaType, poster_url: posterUrl, year })
}

export function fillMissingFromEmby(tmdbId) {
  return apiClient.post('/emby/fill-missing', { tmdb_id: tmdbId })
}

export function getTmdb404List() {
  return apiClient.get('/emby/tmdb-404')
}

export function moveTmdb404Item(tmdbId) {
  return apiClient.post(`/emby/tmdb-404/${tmdbId}/move`)
}

export function resolveTmdb404Path(tmdbId) {
  return apiClient.post(`/emby/tmdb-404/${tmdbId}/resolve`)
}