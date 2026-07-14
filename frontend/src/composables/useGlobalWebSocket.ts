// src/composables/useGlobalWebSocket.ts
import { ref } from 'vue'

export const latestMessage = ref<any>(null)

let connections: WebSocket[] = []
let reconnectTimer: number | null = null
let currentEvents: string[] = []

/**
 * 建立 WebSocket 连接（支持多事件订阅）
 * @param events 要订阅的事件类型列表，默认 ['task_completed', 'experiment_completed']
 */
export function connectWebSocket(events: string[] = ['task_completed', 'experiment_completed']) {
  // 保存当前订阅的事件，用于重连
  currentEvents = events

  // 先彻底断开所有旧连接（同时清除定时器）
  disconnectWebSocket()

  const baseUrl = import.meta.env.VITE_API_BASE_URL.replace('http', 'ws')

  events.forEach(eventType => {
    const url = `${baseUrl}/ws/subscribe/${eventType}`
    const ws = new WebSocket(url)

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        data._eventType = eventType
        latestMessage.value = data
      } catch (err) {
        console.warn('WebSocket 消息解析失败:', err)
      }
    }

    ws.onclose = () => {
      console.log(`WebSocket [${eventType}] 断开，将统一重连...`)
      // 移除已断开的连接
      connections = connections.filter(c => c !== ws)
      // 如果所有连接都断开了，则启动重连（清除旧的定时器，设置新的）
      if (connections.length === 0 && reconnectTimer === null) {
        reconnectTimer = window.setTimeout(() => {
          reconnectTimer = null
          console.log('WebSocket 开始重连...')
          // 重连时重新调用 connectWebSocket，它会先断开旧连接（这里其实已经全部断开了）
          connectWebSocket(currentEvents)
        }, 5000)
      }
    }

    ws.onerror = (err) => {
      console.error(`WebSocket [${eventType}] 错误:`, err)
      ws.close() // 关闭连接，触发 onclose
    }

    connections.push(ws)
  })
}

/**
 * 断开所有 WebSocket 连接，并清除重连定时器
 */
export function disconnectWebSocket() {
  // 清除重连定时器
  if (reconnectTimer !== null) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  // 关闭所有连接
  connections.forEach(ws => {
    // 设置一个空的 onclose 避免触发重连
    ws.onclose = null
    ws.close()
  })
  connections = []
}