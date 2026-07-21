import axios from 'axios'

const apiClient = axios.create({
  baseURL: '/api',
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json',
  },
})

/** 请求拦截器 — 自动附加 Bearer token */
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('unisub_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

/** 统一错误处理 — 使用 AppProvider 注册的 window.$message */
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const msg = error.response?.data?.detail || error.message || '请求失败'
    if (window.$message) {
      // 401 不弹错误，路由守卫会处理跳转登录
      if (error.response?.status !== 401) {
        window.$message.error(msg, { duration: 4000 })
      }
    }
    return Promise.reject(error)
  }
)

export default apiClient