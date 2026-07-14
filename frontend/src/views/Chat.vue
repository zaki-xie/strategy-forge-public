<template>
  <div style="height: 100%; display: flex; flex-direction: column; padding: 20px; box-sizing: border-box;">
    <h2 style="margin: 0 0 8px 0;">量化助手</h2>

    <!-- 模型选择与设置 -->
    <div style="display: flex; align-items: center; gap: 16px; margin-bottom: 16px; flex-shrink: 0;">
      <span>模型：</span>
      <el-select v-model="selectedModel" placeholder="选择模型" style="width: 200px;">
        <el-option v-for="m in models" :key="m.name" :label="`${m.name} (${m.type})`" :value="m.name" />
      </el-select>
      <el-switch v-model="streamMode" active-text="流式" inactive-text="非流式" />
      <el-button @click="clearMessages" size="small" :disabled="messages.length === 0">清空对话</el-button>
    </div>

    <!-- 聊天区域 -->
    <div ref="chatList" class="chat-list">
      <div v-for="(msg, index) in messages" :key="index" :class="['message', msg.role]">
        <el-avatar
          :icon="msg.role === 'user' ? UserFilled : ChatDotRound"
          :style="{ backgroundColor: msg.role === 'user' ? '#409EFF' : '#67C23A' }"
          class="avatar"
        />
        <div class="content" v-html="formatContent(msg.content || (msg.thinking ? '正在思考...' : ''))"></div>
      </div>
      <div v-if="messages.length === 0" class="empty-chat">
        <el-icon :size="48" color="#c0c4cc"><ChatLineRound /></el-icon>
        <p>发送消息开始对话</p>
      </div>
    </div>

    <!-- 输入框 -->
    <div style="display: flex; gap: 8px; flex-shrink: 0;">
      <el-input
        v-model="inputText"
        @keyup.enter="sendMessage"
        placeholder="输入消息..."
        :disabled="sending"
        clearable
      />
      <el-button type="primary" @click="sendMessage" :loading="sending">发送</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, onMounted } from 'vue'
import { getModels, sendChatStream, sendChatNonStream } from '@/api/chat'
import { ElMessage } from 'element-plus'
import { UserFilled, ChatDotRound, ChatLineRound } from '@element-plus/icons-vue'

defineOptions({ name: 'Chat' })

interface Message {
  role: 'user' | 'assistant'
  content: string
  thinking?: boolean    // 是否处于思考状态（等待第一个 token）
}

const messages = ref<Message[]>([])
const inputText = ref('')
const sending = ref(false)
const selectedModel = ref('ollama')
const streamMode = ref(true)
const models = ref<{ name: string; type: string }[]>([])
const chatList = ref<HTMLElement>()

async function fetchModels() {
  try {
    const res = await getModels()
    if (res.code === 0 && res.data) {
      models.value = res.data
      if (models.value.length > 0 && !models.value.find(m => m.name === selectedModel.value)) {
        selectedModel.value = models.value[0].name
      }
    }
  } catch (e) {
    console.error(e)
    ElMessage.error('获取模型列表失败')
  }
}

async function sendMessage() {
  const text = inputText.value.trim()
  if (!text) return

  messages.value.push({ role: 'user', content: text })
  inputText.value = ''
  sending.value = true

  // 添加“思考中”占位消息
  const thinkingMsg: Message = { role: 'assistant', content: '', thinking: true }
  messages.value.push(thinkingMsg)
  const assistantIndex = messages.value.length - 1

  await nextTick()
  scrollToBottom()

  try {
    if (streamMode.value) {
      const response = await sendChatStream({ message: text, model: selectedModel.value })
      if (!response.ok) throw new Error(`HTTP error ${response.status}`)

      const reader = response.body?.getReader()
      if (!reader) throw new Error('无法读取响应流')

      const decoder = new TextDecoder()
      let firstToken = true

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        const chunk = decoder.decode(value, { stream: true })
        const lines = chunk.split('\n').filter(l => l.startsWith('data:'))

        for (const line of lines) {
          const dataStr = line.slice(5).trim()
          if (dataStr === '[DONE]') continue
          try {
            const data = JSON.parse(dataStr)
            if (data.content) {
              // 第一个 token 到达，移除思考状态
              if (firstToken) {
                messages.value[assistantIndex].thinking = false
                firstToken = false
              }
              messages.value[assistantIndex].content += data.content
              await nextTick()
              scrollToBottom()
            }
            if (data.error) {
              messages.value[assistantIndex].content += `\n[错误: ${data.error}]`
              messages.value[assistantIndex].thinking = false
              break
            }
          } catch { /* 忽略解析错误 */ }
        }
      }
    } else {
      const res = await sendChatNonStream({ message: text, model: selectedModel.value })
      if (res.code === 0 && res.data) {
        messages.value[assistantIndex].content = res.data.content
        messages.value[assistantIndex].thinking = false
      } else {
        throw new Error(res.message || '请求失败')
      }
      await nextTick()
      scrollToBottom()
    }
  } catch (err: any) {
    console.error(err)
    messages.value[assistantIndex].content = `出错了: ${err.message}`
    messages.value[assistantIndex].thinking = false
  } finally {
    sending.value = false
    // 如果思考状态仍在（即没有任何 token 返回），清除思考标记
    if (messages.value[assistantIndex]?.thinking) {
      messages.value[assistantIndex].thinking = false
      messages.value[assistantIndex].content = '请求超时或未收到回复，请重试。'
    }
  }
}

function formatContent(text: string) {
  return text.replace(/\n/g, '<br/>')
}

function clearMessages() {
  messages.value = []
}

function scrollToBottom() {
  if (chatList.value) {
    chatList.value.scrollTop = chatList.value.scrollHeight
  }
}

onMounted(() => {
  fetchModels()
})
</script>

<style scoped>
.chat-list {
  flex: 1;
  overflow-y: auto;
  margin-bottom: 16px;
  background: #f9fafc;
  padding: 16px;
  border-radius: 8px;
}

.chat-list .message {
  display: flex;
  margin-bottom: 20px;
  align-items: flex-start;
}

.chat-list .message.user {
  flex-direction: row-reverse;
}

.chat-list .avatar {
  flex-shrink: 0;
}

.chat-list .content {
  max-width: 75%;
  background: white;
  padding: 10px 14px;
  border-radius: 12px;
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.6;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}

.chat-list .message.user .content {
  background: #409EFF;
  color: white;
}

.chat-list .message.assistant .content {
  background: white;
  border: 1px solid #ebeef5;
}

.chat-list .message.user .avatar {
  margin-left: 10px;
}

.chat-list .message.assistant .avatar {
  margin-right: 10px;
}

/* 思考中动画 */
.chat-list .message.assistant .content:empty::after,
.chat-list .message.assistant .content:contains('正在思考...') {
  animation: pulse 1.5s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.empty-chat {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #c0c4cc;
}

.empty-chat p {
  margin-top: 12px;
  font-size: 14px;
}
</style>