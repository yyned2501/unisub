import { ref, onMounted } from 'vue'
import { getTmdb404List, moveTmdb404Item, resolveTmdb404Path } from '@/service/api/emby'
import { getCd2Config } from '@/service/api/cd2'
import type { AxiosError } from 'axios'
import type { Tmdb404Item, Tmdb404ResolveResult } from '@/types'

/** 管理无 TMDB 数据媒体列表的加载和移动操作。 */
export function useTmdb404() {
  const items = ref<Tmdb404Item[]>([])
  const loading = ref(false)
  const movingIds = ref<Set<number>>(new Set())
  const resolvingIds = ref<Set<number>>(new Set())
  const targetPath = ref('')
  const resolvedMap = ref<Record<number, Tmdb404ResolveResult>>({})

  async function loadList() {
    loading.value = true
    try {
      const { data } = await getTmdb404List()
      items.value = Array.isArray(data) ? data : []
    } catch {
      items.value = []
    } finally {
      loading.value = false
    }
  }

  async function loadCd2Config() {
    try {
      const { data } = await getCd2Config()
      targetPath.value = data?.target_path ?? ''
    } catch {
      targetPath.value = ''
    }
  }

  async function handleResolve(item: Tmdb404Item) {
    resolvingIds.value = new Set([...resolvingIds.value, item.tmdb_id])
    try {
      const { data } = await resolveTmdb404Path(item.tmdb_id)
      resolvedMap.value = { ...resolvedMap.value, [item.tmdb_id]: data }
      if (data.verified) {
        window.$message?.success(`CD2 路径确认: ${data.cd2_path}`)
        item.cd2_path = data.cd2_path
      } else {
        window.$message?.warning(data.note || 'CD2 中未找到该路径')
      }
    } catch (e: unknown) {
      const err = e as AxiosError<{ detail?: string }>
      window.$message?.error(err.response?.data?.detail || '路径确认失败')
    } finally {
      const next = new Set(resolvingIds.value)
      next.delete(item.tmdb_id)
      resolvingIds.value = next
    }
  }

  function handleMove(item: Tmdb404Item): Promise<boolean> {
    const resolved = resolvedMap.value[item.tmdb_id]
    const src = resolved?.cd2_path || item.cd2_path || item.emby_path || '未知路径'
    const dst = targetPath.value || '（未配置 CD2 目标路径）'

    return new Promise((resolve, reject) => {
      window.$dialog?.warning({
        title: '确认移动',
        content: `源路径: ${src}\n\n目标路径: ${dst}`,
        positiveText: '确认移动',
        negativeText: '取消',
        onPositiveClick: () => resolve(true),
        onNegativeClick: () => reject(false),
        onClose: () => reject(false),
      })
    })
  }

  async function confirmMove(item: Tmdb404Item) {
    try {
      await handleMove(item)
    } catch {
      return
    }

    movingIds.value = new Set([...movingIds.value, item.tmdb_id])
    try {
      const { data } = await moveTmdb404Item(item.tmdb_id)
      if (data?.success) {
        window.$message?.success(data.message || '移动成功')
        items.value = items.value.filter(i => i.tmdb_id !== item.tmdb_id)
      } else {
        window.$message?.error(data?.message || '移动失败')
      }
    } catch (e: unknown) {
      const err = e as AxiosError<{ detail?: string }>
      window.$message?.error(err.response?.data?.detail || '移动失败')
    } finally {
      const next = new Set(movingIds.value)
      next.delete(item.tmdb_id)
      movingIds.value = next
    }
  }

  onMounted(() => { loadList(); loadCd2Config() })

  return {
    items,
    loading,
    movingIds,
    resolvingIds,
    targetPath,
    resolvedMap,
    loadList,
    handleResolve,
    confirmMove,
  }
}