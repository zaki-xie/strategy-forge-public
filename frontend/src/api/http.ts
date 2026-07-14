import axios from 'axios'
import { ElMessage } from 'element-plus'

const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,   // 读取 .env 中的地址
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// 可选：请求拦截器（以后添加 token 等）
http.interceptors.request.use(
  config => config,
  error => Promise.reject(error)
)

// 可选：响应拦截器（统一处理错误）
http.interceptors.response.use(
  (response) => {
      const body = response.data
      // 如果返回的是统一格式，且业务码为 0，则自动提取 data 部分
      if (body && typeof body === 'object' && 'code' in body) {
        if (body.code === 0) {
          // 成功：返回 data（或整个 body 给组件处理）
          return body
        } else {
          // 业务错误：显示错误消息并抛出
          const errorMsg = body.message || body.detail || '业务处理失败'
          ElMessage.error(errorMsg)   // 显示红色错误提示
          console.warn('API 业务错误:', errorMsg)
          return Promise.reject(body)
        }
      }
      return body
    },
    (error) => {
      // HTTP 错误（如 500, 404, 网络超时等）
      let errorMsg = '请求失败'
      if (error.response) {
        // 后端返回了错误状态码
        const status = error.response.status
        const detail = error.response.data?.detail || error.response.data?.message
        if (status === 500) errorMsg = detail || '服务器内部错误，请稍后重试'
        else if (status === 404) errorMsg = detail || '请求的资源不存在'
        else if (status === 403) errorMsg = detail || '没有权限访问'
        else if (status === 400) errorMsg = detail || '请求参数错误'
        else errorMsg = detail || `请求失败 (${status})`
      } else if (error.request) {
        // 请求已发出，但没有收到响应
        errorMsg = '网络异常，无法连接服务器'
      } else {
        // 请求配置出错
        errorMsg = error.message || '请求配置错误'
      }
      ElMessage.error(errorMsg)   // 显示错误提示
      console.error('HTTP 错误:', error)
      return Promise.reject(error)
    }
)

export default http