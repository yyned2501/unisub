<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { getLogFiles, getLogContent, getDebugInfo } from '@/service/api/logs'
import type { LogFileInfo, DebugInfo } from '@/types'

defineOptions({ name: 'LogViewer' })

const loading = ref(false)
const files = ref<LogFileInfo[]>([])
const selectedFile = ref('unisub.log')
const lines = ref(200)
const filter = ref('')
const logLevel = ref('DEBUG')
const isTail = ref(true)
const reverseOrder = ref(false)
const logLines = ref<string[]>([])
const totalLines = ref(0)
const debugInfo = ref<DebugInfo | null>(null)
const showDebug = ref(false)

const LEVEL_OPTIONS = [
  { value: 'DEBUG', label: 'DEBUG' },
  { value: 'INFO', label: 'INFO' },
  { value: 'WARNING', label: 'WARNING' },
  { value: 'ERROR', label: 'ERROR' },
]

async function loadFiles() {
  try {
    const { data } = await getLogFiles()
    files.value = data.files || []
  } catch {
    window.$message?.error('加载日志文件列表失败')
  }
}

async function loadContent() {
  loading.value = true
  try {
    const { data } = await getLogContent(selectedFile.value, {
      lines: lines.value,
      filter: filter.value,
      level: logLevel.value,
      tail: isTail.value,
    })
    logLines.value = data.lines || []
    totalLines.value = data.total_lines || 0
  } catch {
    window.$message?.error('加载日志内容失败')
    logLines.value = []
    totalLines.value = 0
  } finally {
    loading.value = false
  }
}

async function loadDebug() {
  try {
    const { data } = await getDebugInfo()
    debugInfo.value = data
  } catch {
    window.$message?.error('加载 Debug 信息失败')
  }
}

function refresh() {
  loadContent()
}

function toggleDebug() {
  showDebug.value = !showDebug.value
  if (showDebug.value && !debugInfo.value) {
    loadDebug()
  }
}

function copyLog() {
  navigator.clipboard?.writeText(logLines.value.join('\n'))
    .then(() => window.$message?.success('已复制到剪贴板'))
    .catch(() => window.$message?.error('复制失败'))
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function levelClass(line: string): string {
  if (line.includes('[ERROR]')) return 'log-error'
  if (line.includes('[WARNING]')) return 'log-warn'
  if (line.includes('[DEBUG]')) return 'log-debug'
  return ''
}

const displayLines = computed(() => {
  if (reverseOrder.value) {
    return [...logLines.value].reverse()
  }
  return logLines.value
})

onMounted(() => {
  loadFiles()
  loadContent()
})

watch(selectedFile, () => loadContent())
watch(lines, () => loadContent())
watch(logLevel, () => loadContent())
watch(isTail, () => loadContent())
</script>

<template>
  <div>
    <h2 class="text-lg font-bold mb-4">日志查看</h2>

    <!-- 工具栏 -->
    <n-card :bordered="true" size="small" class="mb-4">
      <div class="flex flex-wrap items-center gap-3">
        <div class="flex items-center gap-1.5">
          <span class="text-xs opacity-50">文件</span>
          <n-select
            v-model:value="selectedFile"
            :options="files.map(f => ({ value: f.name, label: `${f.name} (${formatSize(f.size)})` }))"
            size="small" style="min-width: 200px;" filterable
          />
        </div>

        <div class="flex items-center gap-1.5">
          <span class="text-xs opacity-50">级别</span>
          <n-select v-model:value="logLevel" :options="LEVEL_OPTIONS" size="small" style="width: 100px;" />
        </div>

        <div class="flex items-center gap-1.5">
          <span class="text-xs opacity-50">行数</span>
          <n-select v-model:value="lines" :options="[
            { value: 100, label: '100' },
            { value: 200, label: '200' },
            { value: 500, label: '500' },
            { value: 1000, label: '1000' },
            { value: 2000, label: '2000' },
          ]" size="small" style="width: 90px;" />
        </div>

        <div class="flex items-center gap-1.5">
          <span class="text-xs opacity-50">方向</span>
          <n-switch v-model:value="isTail" size="small">
            <template #checked>尾部</template>
            <template #unchecked>头部</template>
          </n-switch>
        </div>

        <div class="flex items-center gap-1.5">
          <span class="text-xs opacity-50">倒序</span>
          <n-switch v-model:value="reverseOrder" size="small">
            <template #checked>开</template>
            <template #unchecked>关</template>
          </n-switch>
        </div>

        <div class="flex items-center gap-1.5" style="flex: 1; min-width: 150px; max-width: 280px;">
          <span class="text-xs opacity-50">筛选</span>
          <n-input v-model:value="filter" placeholder="关键字" size="small" clearable @keyup.enter="refresh" />
        </div>

        <n-button size="tiny" @click="refresh" :loading="loading">
          <template #icon><i class="ri-refresh-line"></i></template>
          刷新
        </n-button>
        <n-button size="tiny" quaternary @click="copyLog" :disabled="logLines.length === 0">
          <template #icon><i class="ri-clipboard-line"></i></template>
          复制
        </n-button>
        <n-button size="tiny" quaternary @click="toggleDebug">
          <template #icon><i class="ri-bug-line"></i></template>
          {{ showDebug ? '隐藏' : 'Debug' }}
        </n-button>
      </div>
    </n-card>

    <!-- Debug Info -->
    <n-collapse v-if="showDebug" :default-expanded-names="['debug']" class="mb-4">
      <n-collapse-item title="Debug Info" name="debug">
        <n-card size="small" :bordered="false">
          <pre class="text-xs leading-relaxed whitespace-pre-wrap">{{ JSON.stringify(debugInfo, null, 2) || '加载中...' }}</pre>
        </n-card>
      </n-collapse-item>
    </n-collapse>

    <!-- 日志内容 -->
    <n-card :bordered="true" size="small">
      <template #header>
        <div class="flex items-center justify-between">
          <span class="text-sm font-medium">{{ selectedFile }}</span>
          <span class="text-xs opacity-40">共 {{ totalLines }} 行</span>
        </div>
      </template>
      <n-spin :show="loading">
        <div v-if="logLines.length > 0" class="log-viewer">
          <pre
            v-for="(line, i) in displayLines"
            :key="i"
            class="log-line"
            :class="levelClass(line)"
          ><code>{{ line }}</code></pre>
        </div>
        <n-empty v-else description="暂无日志" class="py-8" size="small" />
      </n-spin>
    </n-card>
  </div>
</template>

<style scoped>
.log-viewer {
  font-family: 'Cascadia Code', 'Fira Code', 'JetBrains Mono', monospace;
  font-size: 12px;
  line-height: 1.6;
  max-height: 70vh;
  overflow-y: auto;
  background: #1e1e1e;
  border-radius: 6px;
  padding: 12px;
}

.log-line {
  margin: 0;
  padding: 0;
  white-space: pre-wrap;
  word-break: break-all;
  color: #d4d4d4;
}

.log-line:hover {
  background: rgba(255, 255, 255, 0.05);
}

.log-error {
  color: #f48771;
}

.log-warn {
  color: #cca700;
}

.log-debug {
  color: #6a9955;
}
</style>