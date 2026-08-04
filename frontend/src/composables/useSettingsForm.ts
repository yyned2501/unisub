/**
 * 设置页通用加载/保存状态机。
 *
 * HTTP 错误统一由 request.ts 响应拦截器弹 toast，本模块 catch 不再重复提示；
 * 仅在保存成功时弹 success（业务层语义）。
 */
import { reactive, ref, onMounted } from 'vue'
import { msg } from '@/utils/message'

interface SettingsFormOptions<T extends object> {
  /** 表单默认值 */
  defaults: T
  /** 拉取远端配置，返回要合并进表单的字段 */
  fetch: () => Promise<Partial<T>>
  /** 持久化表单配置（参数是响应式表单对象，可读可写） */
  persist: (config: T) => Promise<unknown>
  /** 保存成功提示 */
  saveSuccessText?: string
}

export function useSettingsForm<T extends object>(options: SettingsFormOptions<T>) {
  const config = reactive({ ...options.defaults }) as T
  const loading = ref(false)
  const saving = ref(false)

  async function loadConfig() {
    loading.value = true
    try {
      Object.assign(config, await options.fetch())
    } catch {
      // 拦截器已统一弹错误消息
    } finally {
      loading.value = false
    }
  }

  /** 保存配置，返回是否成功。 */
  async function saveConfig(): Promise<boolean> {
    saving.value = true
    try {
      await options.persist(config)
      msg.success(options.saveSuccessText ?? '已保存')
      return true
    } catch {
      // 拦截器已统一弹错误消息；返回 false 供调用方门控后续流程
      return false
    } finally {
      saving.value = false
    }
  }

  onMounted(loadConfig)

  return { config, loading, saving, loadConfig, saveConfig }
}
