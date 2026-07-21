<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useMediaQuery } from '@vueuse/core'
import { NConfigProvider, zhCN } from 'naive-ui'
import AppProvider from '@/components/common/app-provider.vue'
import AppMenu from '@/components/common/AppMenu.vue'
import { useThemeStore } from '@/store/modules/theme'
import { useAuthStore } from '@/store/modules/auth'

defineOptions({ name: 'App' })

const themeStore = useThemeStore()
const router = useRouter()
const route = useRoute()

const collapsed = ref(false)
/** 小屏（<768px）：侧边栏改为抽屉式导航 */
const isMobile = useMediaQuery('(max-width: 767px)')
const drawerVisible = ref(false)

const auth = useAuthStore()
const isLoginPage = computed(() => route.path === '/login')

function handleLogout() {
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <NConfigProvider :theme="themeStore.naiveTheme" :locale="zhCN" class="h-full">
    <AppProvider>
      <!-- 登录页 — 不显示侧边栏 -->
      <router-view v-if="isLoginPage" />
      <!-- 主布局 — 侧边栏 + 内容区 -->
      <div v-else style="position: relative; height: 100%">
        <n-layout has-sider position="absolute">
          <!-- 侧边栏（仅桌面端） -->
          <n-layout-sider
            v-if="!isMobile"
            bordered
            :collapsed="collapsed"
            collapse-mode="width"
            :collapsed-width="64"
            :width="200"
            :native-scrollbar="false"
          >
            <div class="flex items-center h-14 px-4 gap-2.5">
              <svg viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg" class="w-7 h-7 shrink-0">
                <rect width="32" height="32" rx="8" fill="#3b82f6" />
                <text
                  x="16"
                  y="22"
                  text-anchor="middle"
                  fill="white"
                  font-size="18"
                  font-weight="bold"
                  font-family="Arial"
                >
                  U
                </text>
              </svg>
              <span v-show="!collapsed" class="text-base font-bold tracking-wide whitespace-nowrap">UniSub</span>
            </div>

            <AppMenu :collapsed="collapsed" />
          </n-layout-sider>

          <!-- 右侧区域 -->
          <n-layout>
            <n-layout-header bordered class="h-14 flex items-center justify-between px-3 sm:px-4">
              <div class="flex items-center gap-2 sm:gap-3">
                <!-- 移动端：打开抽屉导航 -->
                <n-button v-if="isMobile" quaternary size="small" @click="drawerVisible = true">
                  <template #icon>
                    <i class="ri-menu-line text-lg"></i>
                  </template>
                </n-button>
                <!-- 桌面端：折叠侧边栏 -->
                <n-button v-else quaternary size="small" @click="collapsed = !collapsed">
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
                <n-button quaternary size="small" @click="handleLogout">
                  <template #icon>
                    <i class="ri-logout-box-r-line text-lg"></i>
                  </template>
                </n-button>
              </div>
            </n-layout-header>

            <n-layout-content :native-scrollbar="false">
              <div class="p-3 sm:p-5 mx-auto" style="max-width: 1400px">
                <router-view v-slot="{ Component }">
                  <transition name="fade" mode="out-in">
                    <component :is="Component" />
                  </transition>
                </router-view>
              </div>
            </n-layout-content>
          </n-layout>
        </n-layout>

        <!-- 移动端抽屉导航 -->
        <n-drawer v-model:show="drawerVisible" :width="260" placement="left">
          <n-drawer-content :native-scrollbar="false" body-content-style="padding: 0">
            <template #header>
              <div class="flex items-center gap-2.5">
                <svg viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg" class="w-7 h-7 shrink-0">
                  <rect width="32" height="32" rx="8" fill="#3b82f6" />
                  <text
                    x="16"
                    y="22"
                    text-anchor="middle"
                    fill="white"
                    font-size="18"
                    font-weight="bold"
                    font-family="Arial"
                  >
                    U
                  </text>
                </svg>
                <span class="text-base font-bold tracking-wide">UniSub</span>
              </div>
            </template>
            <AppMenu @navigate="drawerVisible = false" />
          </n-drawer-content>
        </n-drawer>
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
