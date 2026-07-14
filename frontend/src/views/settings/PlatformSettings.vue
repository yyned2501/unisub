<script setup>
import { ref, reactive, onMounted } from 'vue'
import { getPlatforms, createPlatform, updatePlatform, deletePlatform, testPlatform } from '@/service/api/platforms'
import { getNextFindQuota } from '@/service/api/dashboard'

defineOptions({ name: 'PlatformSettings' })

const platforms = ref([])
const nfQuota = ref(null)
const testingId = ref(null)
const loading = ref(false)

const dialogVisible = ref(false)
const editingPlatform = ref(null)
const savingForm = ref(false)

const form = reactive({
  name: '',
  base_url: '',
  api_key: '',
  enabled: true,
})

function platformDisplayName(name) {
  return name === 'nextfind' ? 'NextFind' : name === 'moviepilot' ? 'MoviePilot' : name === 'emby' ? 'Emby' : name
}

function maskKey(key) {
  if (!key) return '未设置'
  if (key.length <= 8) return '*'.repeat(key.length)
  return key.slice(0, 4) + '****' + key.slice(-4)
}

async function loadPlatforms() {
  loading.value = true
  try {
    const { data } = await getPlatforms()
    platforms.value = Array.isArray(data) ? data : []
  } finally {
    loading.value = false
  }
}

async function loadQuota() {
  try {
    const { data } = await getNextFindQuota()
    nfQuota.value = data?.remaining ?? data?.quota ?? null
  } catch { nfQuota.value = null }
}

function openAddDialog() {
  editingPlatform.value = null
  form.name = ''
  form.base_url = ''
  form.api_key = ''
  form.enabled = true
  dialogVisible.value = true
}

function openEditDialog(p) {
  editingPlatform.value = p
  Object.assign(form, { name: p.name, base_url: p.base_url, api_key: p.api_key, enabled: p.enabled })
  dialogVisible.value = true
}

async function handleSave() {
  savingForm.value = true
  try {
    const payload = { ...form }
    if (editingPlatform.value) {
      await updatePlatform(editingPlatform.value.id, payload)
      window.$message?.success('平台已更新')
    } else {
      await createPlatform(payload)
      window.$message?.success('平台已添加')
    }
    dialogVisible.value = false
    await loadPlatforms()
  } catch {} finally {
    savingForm.value = false
  }
}

async function handleTest(p) {
  testingId.value = p.id
  try {
    await testPlatform(p.id)
    window.$message?.success(`${platformDisplayName(p.name)} 连接成功`)
  } catch {} finally {
    testingId.value = null
  }
}

async function handleToggle(p, enabled) {
  try {
    await updatePlatform(p.id, { ...p, enabled })
    window.$message?.success(`${platformDisplayName(p.name)} 已${enabled ? '启用' : '禁用'}`)
  } catch { p.enabled = !enabled }
}

async function handleDelete(p) {
  try {
    await new Promise((resolve, reject) => {
      window.$dialog?.warning({
        title: '确认操作',
        content: `确定删除${platformDisplayName(p.name)}配置？`,
        positiveText: '确认',
        negativeText: '取消',
        onPositiveClick: resolve,
        onNegativeClick: reject,
        onClose: reject,
      })
    })
  } catch { return }
  try {
    await deletePlatform(p.id)
    window.$message?.success('平台已删除')
    platforms.value = platforms.value.filter(i => i.id !== p.id)
  } catch {}
}

onMounted(() => { loadPlatforms(); loadQuota() })
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-4">
      <h2 class="text-lg font-bold">平台配置</h2>
      <n-button size="small" @click="openAddDialog">
        <template #icon><i class="ri-add-line"></i></template>
        添加平台
      </n-button>
    </div>

    <n-spin :show="loading">
      <!-- 平台卡片网格 -->
      <div v-if="platforms.length > 0" class="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div v-for="p in platforms" :key="p.id"
          class="rounded-xl p-5 transition-shadow cursor-pointer hover:shadow-lg"
          :style="{ border: '1px solid var(--n-border-color)', background: 'var(--n-card-color)' }"
          @click="openEditDialog(p)">

          <!-- 卡片头部 -->
          <div class="flex items-start justify-between mb-4">
            <div class="flex items-center gap-3">
              <div class="flex items-center justify-center w-11 h-11 rounded-xl shrink-0"
                :style="{ background: p.enabled ? 'rgba(59,130,246,0.12)' : 'var(--n-action-color)' }">
                <i :class="p.name === 'nextfind' ? 'ri-radar-line' : p.name === 'emby' ? 'ri-tv-2-line' : 'ri-movie-2-line'"
                  class="text-xl"
                  :style="{ color: p.enabled ? 'rgb(96,165,250)' : 'var(--n-text-color)' }"></i>
              </div>
              <div>
                <h3 class="text-sm font-semibold">{{ platformDisplayName(p.name) }}</h3>
                <n-switch :value="p.enabled" size="small" @click.stop @update:value="(v) => handleToggle(p, v)" />
              </div>
            </div>
            <n-tag :type="p.enabled ? 'success' : 'error'" size="tiny" round>
              {{ p.enabled ? '已连接' : '未连接' }}
            </n-tag>
          </div>

          <!-- 连接信息 -->
          <div class="space-y-1.5 text-xs mb-4">
            <div class="flex items-center gap-2">
              <span class="opacity-40 w-12 shrink-0">地址</span>
              <span class="font-mono opacity-70 truncate">{{ p.base_url }}</span>
            </div>
            <div class="flex items-center gap-2">
              <span class="opacity-40 w-12 shrink-0">API Key</span>
              <span class="font-mono opacity-50">{{ maskKey(p.api_key) }}</span>
            </div>
            <div v-if="p.name === 'nextfind' && nfQuota !== null" class="flex items-center gap-2">
              <span class="opacity-40 w-12 shrink-0">额度</span>
              <span class="font-semibold" style="color: rgb(96,165,250);">{{ nfQuota }}</span>
            </div>
          </div>

          <!-- 操作按钮 -->
          <div class="flex gap-2 pt-3" :style="{ borderTop: '1px solid var(--n-border-color)' }">
            <n-button size="tiny" secondary :loading="testingId === p.id" @click.stop="handleTest(p)">
              <template #icon><i class="ri-plug-line"></i></template>
              测试
            </n-button>
            <n-button size="tiny" quaternary @click.stop="openEditDialog(p)">
              <template #icon><i class="ri-edit-line"></i></template>
              编辑
            </n-button>
            <n-button size="tiny" quaternary type="error" @click.stop="handleDelete(p)">
              <template #icon><i class="ri-delete-bin-6-line"></i></template>
              删除
            </n-button>
          </div>
        </div>
      </div>

      <n-empty v-else description="暂无平台配置" size="small" class="py-12">
        <template #extra>
          <n-button size="tiny" @click="openAddDialog">添加平台</n-button>
        </template>
      </n-empty>
    </n-spin>

    <!-- 添加/编辑弹窗 -->
    <n-modal :show="dialogVisible" preset="card"
      :title="editingPlatform ? '编辑平台' : '添加平台'"
      style="max-width: 500px;" :mask-closable="false"
      @update:show="(v) => { if (!v) dialogVisible = false }">
      <n-form :model="form" label-placement="left" :label-width="90">
        <n-form-item label="平台名称" path="name" :rule="[{ required: true, message: '请选择平台' }]">
          <n-select v-model:value="form.name" :disabled="!!editingPlatform" placeholder="选择平台"
            :options="[{ label: 'NextFind', value: 'nextfind' }, { label: 'MoviePilot', value: 'moviepilot' }, { label: 'Emby', value: 'emby' }]" />
        </n-form-item>
        <n-form-item label="地址" path="base_url" :rule="[{ required: true, message: '请输入 API 地址' }]">
          <n-input v-model:value="form.base_url" placeholder="http://192.168.31.10:8092" />
        </n-form-item>
        <n-form-item label="API Key" path="api_key" :rule="[{ required: true, message: '请输入 API Key' }]">
          <n-input v-model:value="form.api_key" placeholder="输入 API Key" type="password" show-password-on="click" />
        </n-form-item>
        <n-form-item label="启用">
          <n-switch v-model:value="form.enabled" />
        </n-form-item>
      </n-form>
      <template #footer>
        <div class="flex justify-end gap-2">
          <n-button @click="dialogVisible = false" :disabled="savingForm">取消</n-button>
          <n-button type="primary" :loading="savingForm" @click="handleSave">
            <template #icon><i class="ri-save-line"></i></template>
            保存
          </n-button>
        </div>
      </template>
    </n-modal>
  </div>
</template>
