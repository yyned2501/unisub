import axios from 'axios'

const apiClient = axios.create({
  baseURL: '/api',
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json',
  },
})

/** 统一错误处理 — 使用 AppProvider 注册的 window.$message */
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const message = error.response?.data?.detail || error.message || '请求失败'
    if (window.$message) {
      window.$message.error(message, { duration: 4000 })
    }
    return Promise.reject(error)
  }
)

export default apiClient
