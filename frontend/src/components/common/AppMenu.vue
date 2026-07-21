<script setup lang="ts">
import { ref, computed, watch, h } from 'vue'
import { useRoute, useRouter } from 'vue-router'

defineOptions({ name: 'AppMenu' })

const props = withDefaults(
  defineProps<{
    /** 折叠态（仅桌面侧边栏使用） */
    collapsed?: boolean
  }>(),
  { collapsed: false }
)

const emit = defineEmits<{ navigate: [] }>()

const route = useRoute()
const router = useRouter()

function riIcon(className: string) {
  return () => h('i', { class: className })
}

const menuOptions = [
  { label: '看板', key: '/', icon: riIcon('ri-dashboard-line text-lg') },
  { label: '搜索', key: '/search', icon: riIcon('ri-search-line text-lg') },
  { label: '订阅', key: '/subscriptions', icon: riIcon('ri-rss-line text-lg') },
  { label: '媒体库', key: '/emby', icon: riIcon('ri-tv-2-line text-lg') },
  { label: '自动订阅', key: '/settings/auto-subscribe', icon: riIcon('ri-sparkling-2-line text-lg') },
  { label: '无 TMDB 媒体', key: '/emby/tmdb-404', icon: riIcon('ri-error-warning-line text-lg') },
  {
    label: '设置',
    key: 'settings-group',
    icon: riIcon('ri-settings-3-line text-lg'),
    children: [
      { label: '平台配置', key: '/settings/platforms', icon: riIcon('ri-database-2-line') },
      { label: 'CloudDrive2', key: '/settings/cd2', icon: riIcon('ri-cloud-line') },
      { label: '定时任务', key: '/settings/tasks', icon: riIcon('ri-time-line') },
      { label: '日志查看', key: '/settings/logs', icon: riIcon('ri-file-list-3-line') },
      { label: '账号设置', key: '/settings/account', icon: riIcon('ri-user-settings-line') },
    ],
  },
]

const activeKey = computed(() => route.path)

/** 自动展开设置子菜单 */
const expandedKeys = ref<string[]>([])

watch(
  () => route.path,
  (path) => {
    if (path.startsWith('/settings') && !expandedKeys.value.includes('settings-group')) {
      expandedKeys.value = [...expandedKeys.value, 'settings-group']
    }
  },
  { immediate: true }
)

function handleMenuSelect(key: string) {
  router.push(key)
  // 移动端抽屉内选择后关闭抽屉
  emit('navigate')
}
</script>

<template>
  <n-menu
    :value="activeKey"
    :collapsed="props.collapsed"
    :collapsed-width="64"
    :collapsed-icon-size="20"
    :options="menuOptions"
    v-model:expanded-keys="expandedKeys"
    @update:value="handleMenuSelect"
    class="pt-2"
  />
</template>
