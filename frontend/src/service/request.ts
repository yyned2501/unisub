import axios from 'axios'
import type { AxiosRequestConfig } from 'axios'

const instance = axios.create({
  baseURL: '/api',
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
})

/** 请求拦截器 — 自动附加 Bearer token */
instance.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('unisub_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

/** 响应拦截器 — 解包 response.data + 统一错误处理 */
instance.interceptors.response.use(
  (response) => response.data,
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

/**
 * 类型安全的 HTTP 客户端。
 * 响应拦截器已解包 response.data，所有方法直接返回业务数据 T。
 */
const http = {
  get<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    return instance.get(url, config) as unknown as Promise<T>
  },
  post<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    return instance.post(url, data, config) as unknown as Promise<T>
  },
  put<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    return instance.put(url, data, config) as unknown as Promise<T>
  },
  patch<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    return instance.patch(url, data, config) as unknown as Promise<T>
  },
  delete<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    return instance.delete(url, config) as unknown as Promise<T>
  },
}

export default http
