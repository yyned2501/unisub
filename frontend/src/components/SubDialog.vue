<script setup>
import { ref, watch } from 'vue'
import { onImgError } from '@/utils/format'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  media: { type: Object, default: null },
})

const emit = defineEmits(['update:modelValue', 'confirm'])

const show = ref(props.modelValue)
const loading = ref(false)

watch(() => props.modelValue, (val) => { show.value = val })
watch(show, (val) => { emit('update:modelValue', val) })

function handleConfirm() {
  if (!props.media) return
  loading.value = true
  emit('confirm', props.media, (success) => {
    loading.value = false
    if (success) show.value = false
  })
}
</script>

<template>
  <n-modal :show="show" preset="card" title="确认订阅" style="max-width: 460px;" :mask-closable="false" closable
    @update:show="(val) => { if (!val) show = false }">
    <div v-if="media" class="flex gap-4 items-start mb-4">
      <img :src="media.poster_url || ''" class="w-22.5 h-32 rounded-lg object-cover shrink-0"
        style="background: var(--n-border-color);"
        @error="onImgError" />
      <div class="flex-1 pt-1">
        <h4 class="text-base font-semibold mb-1.5">{{ media.title }}</h4>
        <p class="text-xs opacity-50 mb-2">{{ media.year || '未知年份' }} · {{ media.media_type === 'tv' ? '剧集' : '电影' }}</p>
        <span v-if="media.tmdb_id" class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-lg text-xs font-mono" style="background: var(--n-action-color); opacity: 0.6;">
          <i class="ri-fingerprint-line"></i> TMDB {{ media.tmdb_id }}
        </span>
      </div>
    </div>

    <n-alert type="info" :bordered="false" class="!rounded-xl">
      <template #header>
        <span class="text-xs">订阅后，系统将通过 NextFind 自动搜索资源并追更</span>
      </template>
    </n-alert>

    <template #footer>
      <div class="flex justify-end gap-2">
        <n-button @click="show = false" :disabled="loading">取消</n-button>
        <n-button type="primary" :loading="loading" @click="handleConfirm">
          <template #icon><i class="ri-rss-line"></i></template>
          确认订阅
        </n-button>
      </div>
    </template>
  </n-modal>
</template>
