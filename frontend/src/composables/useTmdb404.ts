import { ref, onMounted } from 'vue'
import { getTmdb404List, moveTmdb404Item, resolveTmdb404Path } from '@/service/api/emby'
import { getCd2Config } from '@/service/api/cd2'
import { msg, confirmDialog } from '@/utils/message'
import { useIdSet } from '@/composables/useIdSet'
import type { AxiosError } from 'axios'
import type { Tmdb404Item, Tmdb404ResolveResult } from '@/types'

/** 管理无 TMDB 数据媒体列表的加载和移动操作。 */
export function useTmdb404() {
  const items = ref<Tmdb404Item[]>([])
  const loading = ref(false)
  const movingIds = useIdSet()
  const resolvingIds = useIdSet()
  const targetPath = ref('')
  const resolvedMap = ref<Record<number, Tmdb404ResolveResult>>({})

  async function loadList() {
    loading.value = true
    try {
      const data = await getTmdb404List()
      items.value = Array.isArray(data) ? data : []
    } catch {
      items.value = []
    } finally {
      loading.value = false
    }
  }

  async function loadCd2Config() {
    try {
      const data = await getCd2Config()
      targetPath.value = data?.target_path ?? ''
    } catch {
      targetPath.value = ''
    }
  }

  async function handleResolve(item: Tmdb404Item) {
    resolvingIds.add(item.tmdb_id)
    try {
      const data = await resolveTmdb404Path(item.tmdb_id)
      resolvedMap.value = { ...resolvedMap.value, [item.tmdb_id]: data }
      if (data.verified) {
        msg.success(`CD2 路径确认: ${data.cd2_path}`)
        item.cd2_path = data.cd2_path
      } else {
        msg.warning(data.note || 'CD2 中未找到该路径')
      }
    } catch (e: unknown) {
      const err = e as AxiosError<{ detail?: string }>
      msg.error(err.response?.data?.detail || '路径确认失败')
    } finally {
      resolvingIds.remove(item.tmdb_id)
    }
  }

  async function confirmMove(item: Tmdb404Item) {
    const resolved = resolvedMap.value[item.tmdb_id]
    const src = resolved?.cd2_path || item.cd2_path || item.emby_path || '未知路径'
    const dst = targetPath.value || '（未配置 CD2 目标路径）'

    try {
      await confirmDialog({
        title: '确认移动',
        content: `源路径: ${src}\n\n目标路径: ${dst}`,
        positiveText: '确认移动',
      })
    } catch {
      return
    }

    movingIds.add(item.tmdb_id)
    try {
      const data = await moveTmdb404Item(item.tmdb_id)
      if (data?.success) {
        msg.success(data.message || '移动成功')
        items.value = items.value.filter((i) => i.tmdb_id !== item.tmdb_id)
      } else {
        msg.error(data?.message || '移动失败')
      }
    } catch (e: unknown) {
      const err = e as AxiosError<{ detail?: string }>
      msg.error(err.response?.data?.detail || '移动失败')
    } finally {
      movingIds.remove(item.tmdb_id)
    }
  }

  onMounted(() => {
    loadList()
    loadCd2Config()
  })

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
