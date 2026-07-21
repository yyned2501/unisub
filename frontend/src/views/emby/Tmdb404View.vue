<script setup lang="ts">
import { computed } from 'vue'
import { useTmdb404 } from '@/composables/useTmdb404'
import { onImgError } from '@/utils/format'

defineOptions({ name: 'Tmdb404View' })

const { items, loading, movingIds, resolvingIds, targetPath, resolvedMap, loadList, handleResolve, confirmMove } = useTmdb404()

const hasItems = computed(() => items.value.length > 0)
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-4">
      <h2 class="text-lg font-bold">无 TMDB 数据媒体</h2>
      <div class="flex items-center gap-2">
        <n-button size="small" secondary :loading="loading" @click="loadList">
          <template #icon><i class="ri-refresh-line"></i></template>
          刷新
        </n-button>
      </div>
    </div>

    <p class="text-sm opacity-55 mb-2">
      Emby 中有缓存记录但 TMDB 中没有对应数据的剧集，通常是因为 Emby 刮削器分配了无效的 TMDB ID。
      请先点击「确认路径」从 CD2 验证实际文件夹位置，确认后再移动。
    </p>
    <p v-if="targetPath" class="text-xs opacity-40 mb-4">
      <i class="ri-folder-transfer-line"></i> 移动目标: {{ targetPath }}
    </p>
    <p v-else class="text-xs text-yellow-500 mb-4">
      <i class="ri-alert-line"></i> 未配置 CD2 移动目标路径，请先在 <router-link to="/settings/cd2" class="underline">CD2 设置</router-link> 中配置。
    </p>

    <n-spin :show="loading">
      <n-empty v-if="!loading && !hasItems"
        description="没有发现无 TMDB 数据的媒体" size="small" class="py-12" />

      <n-card v-if="hasItems" size="small" :bordered="true">
        <n-virtual-list
          :items="items"
          :item-size="96"
          style="max-height: calc(100vh - 260px);"
          key-field="tmdb_id"
        >
          <template #default="{ item: s }">
            <div class="flex items-start gap-3 py-2 px-1"
              :style="{ borderBottom: '1px solid var(--n-border-color)' }">

              <!-- 海报 -->
              <img v-if="s.emby_image_url" :src="s.emby_image_url" :alt="s.emby_series_name"
                class="w-10 h-14 rounded object-cover shrink-0"
                @error="onImgError" />
              <div v-else class="w-10 h-14 rounded flex items-center justify-center shrink-0"
                :style="{ background: 'var(--n-action-color)' }">
                <i class="ri-film-line opacity-40"></i>
              </div>

              <!-- 信息 -->
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2 mb-0.5">
                  <span class="text-sm font-medium truncate">{{ s.emby_series_name || '未知' }}</span>
                  <span v-if="s.emby_year" class="text-xs opacity-40 shrink-0">({{ s.emby_year }})</span>
                </div>

                <div class="flex items-center gap-2 text-xs">
                  <n-tag size="tiny" type="error" round>TMDB 404</n-tag>
                  <span class="opacity-40">|</span>
                  <span class="opacity-50">TMDB ID: {{ s.tmdb_id }}</span>
                </div>

                <!-- CD2 路径状态 -->
                <div class="text-xs mt-1 flex flex-col gap-0.5">
                  <template v-if="resolvedMap[s.tmdb_id]">
                    <div class="text-green-500">
                      <i class="ri-checkbox-circle-line"></i> CD2 已确认:
                      <span class="font-mono">{{ resolvedMap[s.tmdb_id].cd2_path }}</span>
                    </div>
                    <div v-if="resolvedMap[s.tmdb_id].sub_file_names?.length" class="opacity-40">
                      包含 {{ resolvedMap[s.tmdb_id].sub_items }} 个项目
                    </div>
                  </template>
                  <template v-else>
                    <span v-if="s.emby_path" class="truncate opacity-30">
                      <span class="opacity-50">Emby:</span> {{ s.emby_path }}
                    </span>
                    <span v-if="!s.emby_path" class="italic opacity-30">无路径信息</span>
                  </template>
                </div>
              </div>

              <!-- 操作按钮 -->
              <div class="flex items-center gap-1 shrink-0">
                <n-button size="tiny" secondary
                  :loading="resolvingIds.has(s.tmdb_id)"
                  :disabled="!s.emby_path || !!resolvedMap[s.tmdb_id]"
                  @click="handleResolve(s)">
                  <template #icon><i class="ri-search-line"></i></template>
                  确认路径
                </n-button>
                <n-button size="tiny" type="warning" secondary
                  :loading="movingIds.has(s.tmdb_id)"
                  :disabled="!resolvedMap[s.tmdb_id]"
                  @click="confirmMove(s)">
                  <template #icon><i class="ri-folder-transfer-line"></i></template>
                  移动回待整理
                </n-button>
              </div>
            </div>
          </template>
        </n-virtual-list>
      </n-card>
    </n-spin>
  </div>
</template>