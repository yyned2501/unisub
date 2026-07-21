<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useAuthStore } from '@/store/modules/auth'
import { getAuthInfo, updateAuth } from '@/service/api/auth'

defineOptions({ name: 'AccountSettings' })

const auth = useAuthStore()
const saving = ref(false)
const username = ref('')
const password = ref('')
const confirmPassword = ref('')
const errorMsg = ref('')
const successMsg = ref('')

onMounted(async () => {
  try {
    const { data } = await getAuthInfo()
    username.value = data.username || ''
  } catch {
    errorMsg.value = '获取账号信息失败'
  }
})

async function handleSave() {
  errorMsg.value = ''
  successMsg.value = ''

  if (!username.value.trim()) {
    errorMsg.value = '用户名不能为空'
    return
  }
  if (!password.value) {
    errorMsg.value = '密码不能为空'
    return
  }
  if (password.value !== confirmPassword.value) {
    errorMsg.value = '两次输入的密码不一致'
    return
  }

  saving.value = true
  try {
    const { data } = await updateAuth(username.value.trim(), password.value)
    if (data.success) {
      successMsg.value = '账号密码已更新，请重新登录'
      // 3 秒后跳转登录页
      setTimeout(() => {
        auth.logout()
        window.location.hash = '#/login'
        window.location.reload()
      }, 3000)
    } else {
      errorMsg.value = data.message || '保存失败'
    }
  } catch (e: unknown) {
    errorMsg.value = (e as import('axios').AxiosError<{ detail?: string }>)?.response?.data?.detail || '保存失败'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div>
    <h2 class="text-lg font-bold mb-4">账号设置</h2>
    <p class="text-sm text-gray-500 dark:text-gray-400 mb-6">
      修改登录账号密码后需要重新登录。
    </p>

    <n-card :bordered="true" style="max-width: 480px">
      <n-form @submit.prevent="handleSave">
        <n-form-item label="用户名">
          <n-input
            v-model:value="username"
            placeholder="请输入用户名"
            :disabled="saving"
          />
        </n-form-item>

        <n-form-item label="新密码">
          <n-input
            v-model:value="password"
            type="password"
            placeholder="请输入新密码"
            :disabled="saving"
            show-password-on="click"
          />
        </n-form-item>

        <n-form-item label="确认密码">
          <n-input
            v-model:value="confirmPassword"
            type="password"
            placeholder="请再次输入新密码"
            :disabled="saving"
            show-password-on="click"
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
        <n-alert
          v-if="successMsg"
          type="success"
          :title="successMsg"
          class="mb-4"
        />

        <n-button
          type="primary"
          block
          :loading="saving"
          attr-type="submit"
          size="large"
        >
          保存
        </n-button>
      </n-form>
    </n-card>
  </div>
</template>