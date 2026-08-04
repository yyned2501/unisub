/**
 * 跨页面共享的小工具函数。
 */

/**
 * 把可能为空的值归一化为数组。
 * @param data - 数组或 null/undefined
 * @returns 原数组或空数组
 */
export function toArray<T>(data: T[] | null | undefined): T[] {
  return Array.isArray(data) ? data : []
}

/**
 * NextFind 有效额度列表（过滤掉"未开启"的空条目）。
 * @param quota - NextFind 额度字典
 * @returns 有效额度文案列表
 */
export function nfQuotaEntries(quota: Record<string, string> | null | undefined): string[] {
  if (!quota) return []
  return Object.values(quota).filter((v) => v && v !== '未开启')
}
