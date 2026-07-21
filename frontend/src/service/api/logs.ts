import request from '../request'
import type { LogFilesResponse, LogContentResponse, LogContentParams, DebugInfo } from '@/types'

export function getLogFiles() {
  return request.get<LogFilesResponse>('/logs/files')
}

export function getLogContent(
  file: string,
  { lines = 200, filter = '', level = 'DEBUG', tail = true }: LogContentParams = {}
) {
  return request.get<LogContentResponse>('/logs/content', {
    params: { file, lines, filter, level, tail },
  })
}

export function getDebugInfo() {
  return request.get<DebugInfo>('/logs/debug')
}
