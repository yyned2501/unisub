import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { login as loginApi } from '@/service/api/auth'
import type { LoginResponse } from '@/types'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('unisub_token') || '')
  const username = ref(localStorage.getItem('unisub_username') || '')

  const isLoggedIn = computed(() => !!token.value)

  async function doLogin(user: string, pass: string) {
    const data = await loginApi(user, pass)
    token.value = data.access_token
    username.value = user
    localStorage.setItem('unisub_token', data.access_token)
    localStorage.setItem('unisub_username', user)
    return data
  }

  function logout() {
    token.value = ''
    username.value = ''
    localStorage.removeItem('unisub_token')
    localStorage.removeItem('unisub_username')
  }

  function checkAuth(): boolean {
    if (!token.value) return false
    // 简单 JWT 过期检查（解码 payload 看 exp）
    try {
      const payload = JSON.parse(atob(token.value.split('.')[1]))
      if (payload.exp * 1000 < Date.now()) {
        logout()
        return false
      }
      return true
    } catch {
      logout()
      return false
    }
  }

  return { token, username, isLoggedIn, doLogin, logout, checkAuth }
})