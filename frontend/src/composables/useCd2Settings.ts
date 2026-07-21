import { reactive, ref, onMounted } from 'vue'
import { getCd2Config, testCd2Connection, updateCd2Config } from '@/service/api/cd2'

/** 管理 CloudDrive2 设置页的配置与操作状态。 */
export function useCd2Settings() {
  const form = reactive({
    base_url: '',
    api_key: '',
    target_path: '/115open/待整理/转存/',
    path_prefix: '',
    path_replacement: '',
    enabled: true,
  })
  const loading = ref(false)
  const saving = ref(false)
  const testing = ref(false)

  async function loadConfig() {
    loading.value = true
    try {
      const { data } = await getCd2Config()
      Object.assign(form, data)
    } finally {
      loading.value = false
    }
  }

  async function saveConfig() {
    saving.value = true
    try {
      const { data } = await updateCd2Config({
        base_url: form.base_url,
        api_key: form.api_key,
        target_path: form.target_path,
        path_prefix: form.path_prefix,
        path_replacement: form.path_replacement,
        enabled: form.enabled,
      })
      Object.assign(form, data)
      window.$message?.success('CloudDrive2 设置已保存')
    } finally {
      saving.value = false
    }
  }

  async function testConnection() {
    await saveConfig()
    testing.value = true
    try {
      const { data } = await testCd2Connection()
      if (data.success) {
        window.$message?.success(data.message)
      } else {
        window.$message?.error(data.message)
      }
    } finally {
      testing.value = false
    }
  }

  onMounted(loadConfig)

  return {
    form,
    loading,
    saving,
    testing,
    saveConfig,
    testConnection,
  }
}