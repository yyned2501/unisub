import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import { darkTheme, lightTheme } from 'naive-ui'

/**
 * 主题管理 store
 * - 暗色/亮色切换
 * - 持久化到 localStorage
 */
export const useThemeStore = defineStore('theme', () => {
  /** 是否暗色模式 */
  const darkMode = ref(true)

  /** 本地存储 key */
  const STORAGE_KEY = 'unisub-theme'

  /** NaiveUI 主题对象 */
  const naiveTheme = computed(() => (darkMode.value ? darkTheme : null))

  /** 从 localStorage 恢复 */
  function load() {
    try {
      const saved = localStorage.getItem(STORAGE_KEY)
      if (saved !== null) {
        darkMode.value = JSON.parse(saved)
      }
    } catch { /* ignore */ }
  }

  /** 切换主题 */
  function toggleDarkMode() {
    darkMode.value = !darkMode.value
    localStorage.setItem(STORAGE_KEY, JSON.stringify(darkMode.value))
  }

  /** 监听暗色模式，给 html 加 class 用于 UnoCSS 适配 */
  watch(darkMode, (val) => {
    document.documentElement.classList.toggle('dark', val)
  }, { immediate: true })

  // 初始化加载
  load()

  return {
    darkMode,
    naiveTheme,
    toggleDarkMode,
  }
})
