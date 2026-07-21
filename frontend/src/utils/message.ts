/**
 * 统一消息提示 — 收敛 window.$message / window.$dialog 调用。
 * AppProvider 负责注册实例，本模块提供类型安全的快捷方法。
 */

/** 消息提示快捷方法 */
export const msg = {
  success: (content: string) => window.$message?.success(content),
  error: (content: string) => window.$message?.error(content),
  warning: (content: string) => window.$message?.warning(content),
  info: (content: string) => window.$message?.info(content),
}

/**
 * Promise 化的确认对话框。
 * 用户点确认 → resolve(true)；点取消/关闭 → reject(false)。
 *
 * @example
 * try {
 *   await confirmDialog({ content: '确定删除？' })
 *   await deleteItem(id)
 * } catch { return }
 */
export function confirmDialog(options: {
  title?: string
  content: string
  positiveText?: string
  negativeText?: string
}): Promise<boolean> {
  return new Promise((resolve, reject) => {
    window.$dialog?.warning({
      title: options.title ?? '确认操作',
      content: options.content,
      positiveText: options.positiveText ?? '确认',
      negativeText: options.negativeText ?? '取消',
      onPositiveClick: () => resolve(true),
      onNegativeClick: () => reject(false),
      onClose: () => reject(false),
    })
  })
}
