<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/store/modules/auth'

defineOptions({ name: 'LoginView' })

const router = useRouter()
const auth = useAuthStore()

const username = ref('admin')
const password = ref('password')
const loading = ref(false)
const errorMsg = ref('')

async function handleLogin() {
  if (!username.value || !password.value) {
    errorMsg.value = '请输入用户名和密码'
    return
  }
  loading.value = true
  errorMsg.value = ''
  try {
    await auth.doLogin(username.value, password.value)
    router.push('/')
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || '登录失败，请重试'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="flex items-center justify-center min-h-screen bg-gray-50 dark:bg-gray-900">
    <div class="w-full max-w-sm mx-4">
      <!-- Logo -->
      <div class="text-center mb-8">
        <div class="inline-flex items-center justify-center w-14 h-14 rounded-xl bg-blue-500 mb-4">
          <svg viewBox="0 0 32 32" fill="none" class="w-8 h-8">
            <rect width="32" height="32" rx="8" fill="#3b82f6"/>
            <text x="16" y="22" text-anchor="middle" fill="white" font-size="18" font-weight="bold" font-family="Arial">U</text>
          </svg>
        </div>
        <h1 class="text-2xl font-bold text-gray-800 dark:text-gray-100">UniSub</h1>
        <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">统一媒体订阅聚合器</p>
      </div>

      <!-- Login Form -->
      <n-card :bordered="true" class="shadow-sm">
        <n-form @submit.prevent="handleLogin">
          <n-form-item label="用户名">
            <n-input
              v-model:value="username"
              placeholder="请输入用户名"
              :disabled="loading"
              @keyup.enter="handleLogin"
            />
          </n-form-item>

          <n-form-item label="密码">
            <n-input
              v-model:value="password"
              type="password"
              placeholder="请输入密码"
              :disabled="loading"
              show-password-on="click"
              @keyup.enter="handleLogin"
            />
          </n-form-item>

          <n-alert
            v-if="errorMsg"
            type="error"
            :title="errorMsg"
            closable
            class="mb-4"
            @close="errorMsg = ''"
          />

          <n-button
            type="primary"
            block
            :loading="loading"
            attr-type="submit"
            size="large"
          >
            登录
          </n-button>
        </n-form>
      </n-card>

      <p class="text-center text-xs text-gray-400 dark:text-gray-500 mt-6">
        UniSub v0.1.0
      </p>
    </div>
  </div>
</template>