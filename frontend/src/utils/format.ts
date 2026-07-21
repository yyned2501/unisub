/**
 * 通用格式化工具函数。
 */

/**
 * 格式化时间戳为 MM-DD HH:mm 格式。
 * @param ts - 时间戳
 * @returns 格式化后的时间字符串
 */
export function formatTime(ts: string | number | Date | null): string {
  if (!ts) return '-'
  const d = new Date(ts)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/**
 * 格式化时间戳为完整本地化日期时间（含年月日时分秒）。
 * @param ts - 时间戳
 * @returns 格式化后的时间字符串
 */
export function formatDateTime(ts: string | number | Date | null): string {
  if (!ts) return '-'
  try {
    return new Date(ts).toLocaleString('zh-CN')
  } catch {
    return String(ts)
  }
}

/**
 * 图片加载失败时的处理 — 隐藏图片。
 * @param event - 图片 error 事件
 */
export function onImgError(event: Event): void {
  const el = event.target as HTMLImageElement | null
  if (el) el.style.display = 'none'
}
