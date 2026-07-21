<script setup lang="ts">
import { ref, computed, watch, h } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { NConfigProvider, zhCN, useMessage } from 'naive-ui'
import AppProvider from '@/components/common/app-provider.vue'
import { useThemeStore } from '@/store/modules/theme'
import { useAuthStore } from '@/store/modules/auth'

defineOptions({ name: 'App' })

const themeStore = useThemeStore()
const router = useRouter()
const route = useRoute()

const collapsed = ref(false)
const auth = useAuthStore()
const isLoginPage = computed(() => route.path === '/login')

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

watch(() => route.path, (path) => {
  if (path.startsWith('/settings') && !expandedKeys.value.includes('settings-group')) {
    expandedKeys.value = [...expandedKeys.value, 'settings-group']
  }
}, { immediate: true })

function handleMenuSelect(key: string) {
  router.push(key)
}
</script>

<template>
  <NConfigProvider :theme="themeStore.naiveTheme" :locale="zhCN" class="h-full">
    <AppProvider>
      <!-- 登录页 — 不显示侧边栏 -->
      <router-view v-if="isLoginPage" />
      <!-- 主布局 — 侧边栏 + 内容区 -->
      <div v-else style="position: relative; height: 100%;">
        <n-layout has-sider position="absolute">
          <!-- 侧边栏 -->
          <n-layout-sider
            bordered
            :collapsed="collapsed"
            collapse-mode="width"
            :collapsed-width="64"
            :width="200"
            :native-scrollbar="false"
          >
            <div class="flex items-center h-14 px-4 gap-2.5">
              <svg viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg" class="w-7 h-7 shrink-0">
                <rect width="32" height="32" rx="8" fill="#3b82f6"/>
                <text x="16" y="22" text-anchor="middle" fill="white" font-size="18" font-weight="bold" font-family="Arial">U</text>
              </svg>
              <span v-show="!collapsed" class="text-base font-bold tracking-wide whitespace-nowrap">UniSub</span>
            </div>

            <n-menu
              :value="activeKey"
              :collapsed="collapsed"
              :collapsed-width="64"
              :collapsed-icon-size="20"
              :options="menuOptions"
              v-model:expanded-keys="expandedKeys"
              @update:value="handleMenuSelect"
              class="pt-2"
            />
          </n-layout-sider>

          <!-- 右侧区域 -->
          <n-layout>
            <n-layout-header bordered class="h-14 flex items-center justify-between px-4">
              <div class="flex items-center gap-3">
                <n-button quaternary size="small" @click="collapsed = !collapsed">
                  <template #icon>
                    <i :class="collapsed ? 'ri-menu-unfold-line' : 'ri-menu-fold-line'" class="text-lg"></i>
                  </template>
                </n-button>
                <span class="text-sm opacity-60 hidden sm:inline">统一媒体订阅聚合器</span>
              </div>

              <div class="flex items-center gap-2">
                <span class="text-xs opacity-50 hidden sm:inline">{{ auth.username }}</span>
                <n-button quaternary size="small" @click="themeStore.toggleDarkMode()">
                  <template #icon>
                    <i :class="themeStore.darkMode ? 'ri-sun-line' : 'ri-moon-line'" class="text-lg"></i>
                  </template>
                </n-button>
                <n-button quaternary size="small" @click="auth.logout(); router.push('/login')">
                  <template #icon>
                    <i class="ri-logout-box-r-line text-lg"></i>
                  </template>
                </n-button>
              </div>
            </n-layout-header>

            <n-layout-content :native-scrollbar="false">
              <div class="p-5 mx-auto" style="max-width: 1400px">
                <router-view v-slot="{ Component }">
                  <transition name="fade" mode="out-in">
                    <component :is="Component" />
                  </transition>
                </router-view>
              </div>
            </n-layout-content>
          </n-layout>
        </n-layout>
      </div>
    </AppProvider>
  </NConfigProvider>
</template>

<style>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
