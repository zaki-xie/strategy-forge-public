import http from './http'
import type { ApiResponse } from './types'

export interface ModelInfo {
  name: string
  type: string
}

// 获取可用模型列表
export const getModels = (): Promise<ApiResponse<ModelInfo[]>> =>
  http.get('/chat/models')

// 非流式发送消息（使用 axios 封装）
export const sendChatNonStream = (data: {
  message: string
  model?: string
  system_prompt?: string
}): Promise<ApiResponse<{ content: string }>> =>
  http.post('/chat/send', { ...data, stream: false })

// 流式发送消息（使用原生 fetch，因为需要读取 SSE 流）
export const sendChatStream = (data: {
  message: string
  model?: string
  system_prompt?: string
}) => {
  const baseURL = import.meta.env.VITE_API_BASE_URL || ''
  return fetch(`${baseURL}/chat/send`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...data, stream: true }),
  })
}