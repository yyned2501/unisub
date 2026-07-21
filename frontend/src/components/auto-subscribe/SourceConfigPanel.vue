<script setup>
import { computed } from 'vue'
import { NCard, NSwitch, NInput, NInputNumber, NSelect } from 'naive-ui'

defineOptions({ name: 'SourceConfigPanel' })

const props = defineProps({
  /** 'douban' | 'mikan' | 'maoyan' */
  source: {
    type: String,
    required: true,
    validator: (v) => ['douban', 'mikan', 'maoyan'].includes(v),
  },
  /** 全局配置对象（reactive），子组件直接绑定其属性 */
  config: { type: Object, required: true },
  /** 元数据（榜单选项、平台列表等） */
  meta: { type: Object, required: true },
  /** 卡片标题 */
  title: { type: String, required: true },
})

const emit = defineEmits(['toggle-array'])

const enabledKey = computed(() => `${props.source}_enabled`)
</script>

<template>
  <n-card :title="title" size="small" :bordered="true" class="mb-4">
    <div class="flex flex-col gap-4">
      <div class="flex items-center justify-between">
        <label class="text-xs opacity-50 font-medium">启用</label>
        <n-switch v-model:value="config[enabledKey]" />
      </div>

      <!-- 豆瓣 -->
      <template v-if="source === 'douban' && config.douban_enabled">
        <div class="flex flex-col gap-1.5">
          <label class="text-xs opacity-50 font-medium">榜单类型</label>
          <div class="flex flex-wrap gap-2">
            <label
              v-for="r in (meta?.douban_ranks || [])" :key="r.value"
              class="flex items-center gap-1.5 px-2.5 py-1 text-xs rounded cursor-pointer"
              :class="config.douban_ranks?.includes(r.value) ? 'bg-blue-500 text-white' : 'bg-gray-100 dark:bg-gray-800'"
              @click="emit('toggle-array', 'douban_ranks', r.value)"
            >
              {{ r.label }}
            </label>
          </div>
        </div>
        <div class="flex flex-col gap-1.5">
          <label class="text-xs opacity-50 font-medium">RSSHub 地址</label>
          <n-input v-model:value="config.douban_rsshub" placeholder="https://rsshub.app" size="small" style="max-width: 300px;" />
        </div>
        <div class="flex flex-col gap-1.5">
          <label class="text-xs opacity-50 font-medium">自定义 RSS（可选，每行一个）</label>
          <n-input v-model:value="config.douban_rss_custom" type="textarea" :rows="2" placeholder="可选" size="small" style="max-width: 400px;" />
        </div>
      </template>

      <!-- Mikan -->
      <template v-if="source === 'mikan' && config.mikan_enabled">
        <div class="flex flex-wrap items-center gap-3">
          <div class="flex items-center gap-1.5">
            <span class="text-xs opacity-50">季度</span>
            <n-select v-model:value="config.mikan_season" :options="meta?.seasons || []" size="small" style="width: 110px;" />
          </div>
          <div class="flex items-center gap-1.5">
            <span class="text-xs opacity-50">年份（0=自动）</span>
            <n-input-number v-model:value="config.mikan_year" :min="0" :max="2100" size="small" style="width: 110px;" />
          </div>
          <div class="flex items-center gap-2">
            <n-switch v-model:value="config.mikan_resolve_detail" size="small" />
            <span class="text-xs opacity-50">解析详情</span>
          </div>
        </div>
      </template>

      <!-- 猫眼 -->
      <template v-if="source === 'maoyan' && config.maoyan_enabled">
        <div class="flex items-center gap-2">
          <n-switch v-model:value="config.maoyan_movie_box" size="small" />
          <span class="text-xs opacity-50">实时票房榜</span>
        </div>
        <div class="flex items-center gap-1.5">
          <span class="text-xs opacity-50">网播榜条数</span>
          <n-input-number v-model:value="config.maoyan_num" :min="1" :max="50" size="small" style="width: 100px;" />
        </div>
        <div class="flex flex-col gap-1.5">
          <label class="text-xs opacity-50 font-medium">平台</label>
          <div class="flex flex-wrap gap-2">
            <label
              v-for="p in (meta?.maoyan_platforms || [])" :key="p.value"
              class="flex items-center gap-1.5 px-2.5 py-1 text-xs rounded cursor-pointer"
              :class="config.maoyan_web_platforms?.includes(p.value) ? 'bg-blue-500 text-white' : 'bg-gray-100 dark:bg-gray-800'"
              @click="emit('toggle-array', 'maoyan_web_platforms', p.value)"
            >
              {{ p.label }}
            </label>
          </div>
        </div>
        <div class="flex flex-col gap-1.5">
          <label class="text-xs opacity-50 font-medium">媒体类型</label>
          <div class="flex flex-wrap gap-2">
            <label
              v-for="t in (meta?.maoyan_media_types || [])" :key="t.value"
              class="flex items-center gap-1.5 px-2.5 py-1 text-xs rounded cursor-pointer"
              :class="config.maoyan_web_types?.includes(t.value) ? 'bg-blue-500 text-white' : 'bg-gray-100 dark:bg-gray-800'"
              @click="emit('toggle-array', 'maoyan_web_types', t.value)"
            >
              {{ t.label }}
            </label>
          </div>
        </div>
      </template>
    </div>
  </n-card>
</template>