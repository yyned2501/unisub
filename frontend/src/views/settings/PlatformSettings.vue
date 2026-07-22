<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { getPlatforms, updatePlatform, deletePlatform, testPlatform } from '@/service/api/platforms'
import { getNextFindQuota } from '@/service/api/dashboard'
import { msg, confirmDialog } from '@/utils/message'
import type { PlatformConfig } from '@/types'

defineOptions({ name: 'PlatformSettings' })

const platforms = ref<PlatformConfig[]>([])
const nfQuota = ref<Record<string, string> | null>(null)
const testingId = ref<string | null>(null)
const loading = ref(false)
const savingId = ref<string | null>(null)

const platformMeta: Record<string, { icon: string; label: string; color: string }> = {
  nextfind: { icon: 'ri-radar-line', label: 'NextFind', color: 'rgb(96,165,250)' },
  moviepilot: { icon: 'ri-movie-2-line', label: 'MoviePilot', color: 'rgb(251,146,60)' },
  emby: { icon: 'ri-tv-2-line', label: 'Emby', color: 'rgb(129,140,248)' },
  tmdb: { icon: 'ri-database-2-line', label: 'TMDB', color: 'rgb(52,211,153)' },
}

function meta(p: PlatformConfig) {
  return platformMeta[p.name] || { icon: 'ri-apps-line', label: p.name, color: 'var(--n-text-color)' }
}

const sortedPlatforms = computed(() => {
  const order = ['nextfind', 'moviepilot', 'emby', 'tmdb']
  return [...platforms.value].sort((a, b) => order.indexOf(a.name) - order.indexOf(b.name))
})

async function loadPlatforms() {
  loading.value = true
  try {
    const data = await getPlatforms()
    platforms.value = Array.isArray(data) ? data : []
  } finally {
    loading.value = false
  }
}

async function loadQuota() {
  try {
    const data = await getNextFindQuota()
    nfQuota.value = data?.quota?.data ?? null
  } catch {
    nfQuota.value = null
  }
}

/** NextFind 有效额度列表（过滤掉"未开启"的空条目） */
const nfQuotaList = computed(() => {
  if (!nfQuota.value) return []
  return Object.values(nfQuota.value).filter((v) => v && v !== '未开启')
})

async function handleSave(p: PlatformConfig) {
  savingId.value = p.id
  try {
    await updatePlatform(p.id, { base_url: p.base_url, api_key: p.api_key, enabled: p.enabled })
    msg.success(`${meta(p).label} 已保存`)
  } catch {
    msg.error(`${meta(p).label} 保存失败`)
  } finally {
    savingId.value = null
  }
}

async function handleTest(p: PlatformConfig) {
  testingId.value = p.id
  try {
    await testPlatform(p.id)
    msg.success(`${meta(p).label} 连接成功`)
  } catch {
    msg.error(`${meta(p).label} 连接失败`)
  } finally {
    testingId.value = null
  }
}

async function handleToggle(p: PlatformConfig, enabled: boolean) {
  p.enabled = enabled
  try {
    await updatePlatform(p.id, { enabled })
    msg.success(`${meta(p).label} 已${enabled ? '启用' : '禁用'}`)
  } catch {
    p.enabled = !enabled
    msg.error(`${meta(p).label} ${enabled ? '启用' : '禁用'}失败`)
  }
}

async function handleDelete(p: PlatformConfig) {
  try {
    await confirmDialog({ content: `确定删除${meta(p).label}配置？` })
  } catch {
    return
  }
  try {
    await deletePlatform(p.id)
    msg.success(`${meta(p).label} 已删除`)
    platforms.value = platforms.value.filter((i) => i.id !== p.id)
  } catch {
    msg.error(`${meta(p).label} 删除失败`)
  }
}

onMounted(() => {
  loadPlatforms()
  loadQuota()
})
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-4">
      <h2 class="text-lg font-bold">平台配置</h2>
    </div>

    <n-spin :show="loading">
      <!-- 平铺卡片网格 -->
      <div v-if="sortedPlatforms.length > 0" class="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div
          v-for="p in sortedPlatforms"
          :key="p.id"
          class="rounded-xl p-5 transition-shadow"
          :style="{ border: '1px solid var(--n-border-color)', background: 'var(--n-card-color)' }"
        >
          <!-- 卡片头部 -->
          <div class="flex items-start justify-between mb-4">
            <div class="flex items-center gap-3">
              <div
                class="flex items-center justify-center w-11 h-11 rounded-xl shrink-0"
                :style="{ background: p.enabled ? 'rgba(59,130,246,0.12)' : 'var(--n-action-color)' }"
              >
                <i
                  :class="meta(p).icon"
                  class="text-xl"
                  :style="{ color: p.enabled ? meta(p).color : 'var(--n-text-color)' }"
                ></i>
              </div>
              <div>
                <h3 class="text-sm font-semibold">{{ meta(p).label }}</h3>
                <n-switch :value="p.enabled" size="small" @update:value="(v) => handleToggle(p, v)" />
              </div>
            </div>
            <n-tag v-if="p.name === 'tmdb'" size="tiny" type="info" round>配置</n-tag>
            <n-tag v-else :type="p.enabled ? 'success' : 'error'" size="tiny" round>
              {{ p.enabled ? '已连接' : '未连接' }}
            </n-tag>
          </div>

          <!-- 内联表单 -->
          <div class="space-y-3">
            <div>
              <label class="text-xs opacity-50 mb-1 block">API 地址</label>
              <n-input v-model:value="p.base_url" size="small" placeholder="API 地址" />
            </div>
            <div>
              <label class="text-xs opacity-50 mb-1 block">API Key</label>
              <n-input
                v-model:value="p.api_key"
                size="small"
                placeholder="API Key"
                type="password"
                show-password-on="click"
              />
            </div>
            <div v-if="p.name === 'nextfind' && nfQuotaList.length" class="flex items-center gap-2 text-xs">
              <span class="opacity-40">额度</span>
              <span class="font-semibold leading-relaxed" style="color: rgb(96, 165, 250)">
                <span v-for="(item, idx) in nfQuotaList" :key="idx" class="block">{{ item }}</span>
              </span>
            </div>
          </div>

          <!-- 操作按钮 -->
          <div class="flex gap-2 pt-4" :style="{ borderTop: '1px solid var(--n-border-color)' }">
            <n-button size="tiny" secondary :loading="savingId === p.id" @click="handleSave(p)">
              <template #icon><i class="ri-save-line"></i></template>
              保存
            </n-button>
            <n-button
              v-if="p.name !== 'tmdb'"
              size="tiny"
              quaternary
              :loading="testingId === p.id"
              @click="handleTest(p)"
            >
              <template #icon><i class="ri-plug-line"></i></template>
              测试
            </n-button>
            <n-button v-if="p.name !== 'tmdb'" size="tiny" quaternary type="error" @click="handleDelete(p)">
              <template #icon><i class="ri-delete-bin-6-line"></i></template>
              删除
            </n-button>
          </div>
        </div>
      </div>

      <n-empty v-else description="暂无平台配置" size="small" class="py-12" />
    </n-spin>
  </div>
</template>
