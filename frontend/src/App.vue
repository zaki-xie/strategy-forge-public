<template>
  <!-- <HelloWorld /> -->
  <router-view />
</template>

<script setup lang="ts">
// import { useWebSocket } from '@/composables/useWebSocket'
// import { ElNotification } from 'element-plus'

// useWebSocket('task_completed', (data) => {
//   ElNotification({
//     title: '任务完成',
//     message: data.message,
//     type: data.type || 'success',
//   })
// })

import { watch } from 'vue'
import { connectWebSocket, latestMessage } from '@/composables/useGlobalWebSocket'
import { ElNotification } from 'element-plus'

connectWebSocket(['task_completed', 'experiment_completed'])

watch(latestMessage, (msg) => {
  if (!msg) return

  // 提取实际的通知数据
  const payload = msg.data || msg      // 兼容不同消息格式
  const type = payload.type
  const message = payload.message

  if (type === 'success' || type === 'error') {
    ElNotification({
      title: type === 'success' ? '成功' : '失败',
      message: message || '操作完成',
      type: type || 'info',
      duration: 5000,
    })
  }
})
</script>