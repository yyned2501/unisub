<script setup lang="ts">
import { onImgError } from '@/utils/format'
import type { EmbyCacheResponse } from '@/types'

defineProps<{
  s: EmbyCacheResponse
  hiding: boolean
  subscribing: boolean
  deleting: boolean
}>()

defineEmits<{
  hide: [tmdbId: number]
  unhide: [tmdbId: number]
  subscribe: [s: EmbyCacheResponse]
  delete: [s: EmbyCacheResponse]
}>()
</script>

<template>
  <div class="flex items-start gap-3 py-2.5 px-1" :class="{ 'opacity-50': s.is_blacklisted }">
    <!-- 海报 -->
    <img
      v-if="s.emby_image_url"
      :src="s.emby_image_url"
      :alt="s.emby_series_name ?? undefined"
      class="w-10 h-14 rounded object-cover shrink-0"
      @error="onImgError"
    />
    <img
      v-else-if="s.poster_url"
      :src="s.poster_url"
      :alt="s.emby_series_name ?? undefined"
      class="w-10 h-14 rounded object-cover shrink-0"
    />
    <div
      v-else
      class="w-10 h-14 rounded flex items-center justify-center shrink-0"
      :style="{ background: 'var(--n-action-color)' }"
    >
      <i class="ri-film-line opacity-40"></i>
    </div>

    <!-- 信息 -->
    <div class="flex-1 min-w-0">
      <div class="flex items-center gap-2 mb-0.5">
        <a
          :href="`https://www.themoviedb.org/tv/${s.tmdb_id}`"
          target="_blank"
          rel="noopener noreferrer"
          class="text-sm font-medium truncate text-primary hover:underline cursor-pointer"
          :title="`在 TMDB 查看：${s.emby_series_name || '未知'}`"
        >{{ s.emby_series_name || '未知' }}</a>
        <span v-if="s.emby_year" class="text-xs opacity-40 shrink-0">({{ s.emby_year }})</span>
        <n-tag v-if="s.emby_library_name" size="tiny" type="info" round class="shrink-0">{{
          s.emby_library_name
        }}</n-tag>
      </div>

      <div class="flex items-center gap-2 text-xs">
        <n-tag v-if="s.is_subscribed" size="tiny" type="success" round>已订阅</n-tag>
        <n-tag v-else size="tiny" type="default" round>未订阅</n-tag>

        <span class="opacity-40">|</span>
        <span class="opacity-50">Emby: {{ s.emby_episode_count ?? 0 }} 集</span>

        <template v-if="s.tmdb_aired_eps !== null">
          <span class="opacity-40">|</span>
          <span class="text-green-500">已播出 {{ s.tmdb_aired_eps }} 集</span>
        </template>
        <template v-else-if="s.tmdb_total_eps !== null">
          <span class="opacity-40">|</span>
          <span class="text-green-500">TMDB 共 {{ s.tmdb_total_eps }} 集</span>
        </template>

        <span v-if="s.adjusted_missing !== null && s.adjusted_missing > 0" class="text-yellow-500 font-medium">
          | 缺: {{ s.adjusted_missing }}
        </span>

        <span v-if="s.tmdb_next_air_date" class="opacity-40">| 下一集: {{ s.tmdb_next_air_date }}</span>
      </div>

      <div v-if="s.overview" class="text-xs opacity-30 mt-0.5 truncate">{{ s.overview }}</div>
    </div>

    <!-- 操作按钮 -->
    <div class="flex items-center gap-1 shrink-0">
      <n-button
        v-if="!s.is_subscribed"
        size="tiny"
        type="primary"
        secondary
        :loading="subscribing"
        @click="$emit('subscribe', s)"
      >
        <template #icon><i class="ri-add-line"></i></template>
        <span class="hidden sm:inline">添加订阅</span>
      </n-button>
      <n-button
        size="tiny"
        quaternary
        type="error"
        :loading="deleting"
        title="从 Emby 删除"
        @click="$emit('delete', s)"
      >
        <template #icon><i class="ri-delete-bin-line"></i></template>
      </n-button>
      <n-button v-if="!s.is_blacklisted" size="tiny" quaternary :loading="hiding" @click="$emit('hide', s.tmdb_id)">
        <template #icon><i class="ri-eye-off-line"></i></template>
      </n-button>
      <n-button v-else size="tiny" quaternary type="warning" :loading="hiding" @click="$emit('unhide', s.tmdb_id)">
        <template #icon><i class="ri-eye-line"></i></template>
      </n-button>
    </div>
  </div>
</template>
