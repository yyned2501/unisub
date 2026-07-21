import request from '../request'

export function getLogFiles() {
  return request.get('/logs/files')
}

export function getLogContent(file, { lines = 200, filter = '', level = 'DEBUG', tail = true } = {}) {
  return request.get('/logs/content', {
    params: { file, lines, filter, level, tail },
  })
}

export function getDebugInfo() {
  return request.get('/logs/debug')
}