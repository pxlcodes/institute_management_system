<script setup>
import { ref } from 'vue'
import { api } from '@/api/client'
import { Sparkles, X, Send, Bot, User } from 'lucide-vue-next'

const isOpen = ref(false)
const inputQuery = ref('')
const loading = ref(false)
const messages = ref([
  { role: 'assistant', text: 'Namaste! I am the ELH Institute AI Assistant. Ask me about attendance, student dues, accounts, or routines.' }
])

const quickCommands = [
  { label: 'Absent Today', cmd: '/absent' },
  { label: 'Fee Dues', cmd: '/dues' },
  { label: 'Accounts', cmd: '/accounts' },
  { label: 'Routines', cmd: '/routines' }
]

async function sendQuery(queryText) {
  const text = queryText || inputQuery.value.trim()
  if (!text) return

  messages.value.push({ role: 'user', text })
  inputQuery.value = ''
  loading.value = true

  try {
    const res = await api('/assistant/chat', {
      method: 'POST',
      body: JSON.stringify({ message: text })
    })
    messages.value.push({ role: 'assistant', text: res.reply || res.text || 'Command executed.' })
  } catch (err) {
    messages.value.push({ role: 'assistant', text: 'Error: ' + err.message })
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="elh-assistant-root">
    <!-- Floating Trigger Bubble -->
    <button 
      @click="isOpen = !isOpen"
      class="assistant-trigger-btn"
      title="AI Institute Assistant"
      aria-label="Open AI Assistant"
    >
      <Sparkles class="trigger-icon" />
    </button>

    <!-- Chat Modal Window -->
    <div v-if="isOpen" class="assistant-window">
      <!-- Header -->
      <div class="assistant-header">
        <div class="assistant-title">
          <Bot class="bot-icon" />
          <span>ELH Assistant</span>
        </div>
        <button @click="isOpen = false" class="close-btn" aria-label="Close">
          <X style="width:16px;height:16px;" />
        </button>
      </div>

      <!-- Quick Action Pills -->
      <div class="quick-pills-bar">
        <button 
          v-for="qc in quickCommands" 
          :key="qc.label"
          @click="sendQuery(qc.cmd)"
          class="pill-btn"
        >
          {{ qc.label }}
        </button>
      </div>

      <!-- Messages Stream -->
      <div class="messages-container">
        <div 
          v-for="(m, idx) in messages" 
          :key="idx"
          :class="['msg-row', m.role === 'user' ? 'msg-user' : 'msg-bot']"
        >
          <div class="msg-bubble">
            {{ m.text }}
          </div>
        </div>
        <div v-if="loading" class="thinking-indicator">
          Thinking...
        </div>
      </div>

      <!-- Input Bar -->
      <form @submit.prevent="sendQuery()" class="input-form">
        <input 
          type="text" 
          v-model="inputQuery"
          placeholder="Ask /dues, /absent, /routines..."
          class="chat-input"
        />
        <button type="submit" class="send-btn" aria-label="Send">
          <Send style="width:14px;height:14px;" />
        </button>
      </form>
    </div>
  </div>
</template>

<style scoped>
.elh-assistant-root {
  font-family: var(--font-family, 'Outfit', sans-serif);
}

.assistant-trigger-btn {
  position: fixed;
  bottom: 24px;
  right: 24px;
  width: 52px;
  height: 52px;
  border-radius: 50%;
  background: linear-gradient(135deg, #0284c7 0%, #0369a1 100%);
  color: #ffffff;
  border: none;
  box-shadow: 0 10px 25px -4px rgba(2, 132, 199, 0.45), 0 4px 10px -2px rgba(2, 132, 199, 0.3);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  z-index: 9999;
  transition: transform 0.2s cubic-bezier(0.4, 0, 0.2, 1), box-shadow 0.2s ease;
}

.assistant-trigger-btn:hover {
  transform: scale(1.08) translateY(-2px);
  box-shadow: 0 14px 28px -4px rgba(2, 132, 199, 0.55);
}

.trigger-icon {
  width: 22px;
  height: 22px;
  animation: pulse 2.5s infinite;
}

@keyframes pulse {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.12); opacity: 0.85; }
}

.assistant-window {
  position: fixed;
  bottom: 86px;
  right: 24px;
  width: 360px;
  max-width: calc(100vw - 40px);
  height: 480px;
  max-height: calc(100vh - 110px);
  background: var(--bg-card, #ffffff);
  border-radius: 18px;
  border: 1px solid var(--line, #e2e8f0);
  box-shadow: 0 20px 40px -10px rgba(0, 0, 0, 0.25), 0 0 0 1px rgba(0,0,0,0.05);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  z-index: 9999;
  animation: slideUp 0.2s ease-out;
}

@keyframes slideUp {
  from { opacity: 0; transform: translateY(12px) scale(0.97); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}

.assistant-header {
  padding: 14px 16px;
  background: linear-gradient(135deg, #090d16 0%, #0c1a30 50%, #0369a1 100%);
  color: #ffffff;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.assistant-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 800;
  font-size: 14px;
  letter-spacing: -0.01em;
}

.bot-icon {
  width: 18px;
  height: 18px;
  color: #7dd3fc;
}

.close-btn {
  background: transparent;
  border: none;
  color: rgba(255, 255, 255, 0.8);
  cursor: pointer;
  padding: 4px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.close-btn:hover {
  background: rgba(255, 255, 255, 0.15);
  color: #ffffff;
}

.quick-pills-bar {
  padding: 8px 12px;
  background: var(--bg-body, #f8fafc);
  border-bottom: 1px solid var(--line, #e2e8f0);
  display: flex;
  gap: 6px;
  overflow-x: auto;
}

.pill-btn {
  padding: 3px 10px;
  border-radius: 9999px;
  background: var(--bg-card, #ffffff);
  border: 1px solid var(--line, #e2e8f0);
  color: var(--muted, #64748b);
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
  cursor: pointer;
  transition: all 0.15s ease;
}

.pill-btn:hover {
  background: #f0f9ff;
  color: #0284c7;
  border-color: #bae6fd;
}

.messages-container {
  flex: 1;
  padding: 14px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.msg-row {
  display: flex;
}

.msg-user {
  justify-content: flex-end;
}

.msg-bot {
  justify-content: flex-start;
}

.msg-bubble {
  max-width: 82%;
  padding: 9px 13px;
  border-radius: 14px;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}

.msg-user .msg-bubble {
  background: #0284c7;
  color: #ffffff;
  border-bottom-right-radius: 3px;
}

.msg-bot .msg-bubble {
  background: var(--bg-hover, #f1f5f9);
  color: var(--ink, #1e293b);
  border-bottom-left-radius: 3px;
}

body.dark .msg-bot .msg-bubble {
  background: #1e293b;
  color: #f1f5f9;
}

.thinking-indicator {
  font-size: 11.5px;
  color: var(--muted, #94a3b8);
  font-style: italic;
  text-align: center;
  margin: 4px 0;
}

.input-form {
  padding: 10px 12px;
  background: var(--bg-card, #ffffff);
  border-top: 1px solid var(--line, #e2e8f0);
  display: flex;
  align-items: center;
  gap: 8px;
}

.chat-input {
  flex: 1;
  padding: 8px 12px !important;
  border: 1px solid var(--line, #e2e8f0) !important;
  border-radius: 8px !important;
  font-size: 12.5px !important;
  background: var(--bg-input, #ffffff) !important;
  color: var(--ink, #1e293b) !important;
  outline: none;
}

.chat-input:focus {
  border-color: #0284c7 !important;
  box-shadow: 0 0 0 2px rgba(2, 132, 199, 0.15) !important;
}

.send-btn {
  padding: 8px 12px;
  background: #0284c7;
  color: #ffffff;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s ease;
}

.send-btn:hover {
  background: #0369a1;
}
</style>
