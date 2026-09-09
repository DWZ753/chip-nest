// HAL 连接状态：WebSocket 推送 + 失败降级红点
import { defineStore } from 'pinia'
import { ref } from 'vue'

import { api } from '../api/client'
import { openStatusSocket, type StatusSocketHandle } from '../api/ws'
import type { AdapterStatus } from '../api/types'

function offline(): AdapterStatus {
  return { mode: 'mock', connected: false, device: null, error: '未连接到后端' }
}

export const useConnectionStore = defineStore('connection', () => {
  const status = ref<AdapterStatus>(offline())
  const socketOpen = ref(false)
  const version = ref<string | null>(null)
  let handle: StatusSocketHandle | null = null

  async function fetchHealth() {
    try {
      const info = await api.health()
      version.value = info.version ?? null
    } catch { /* 后端未就绪时保持空 */ }
  }

  function connect() {
    if (handle) return
    handle = openStatusSocket(
      (next) => { status.value = next; socketOpen.value = true },
      () => { socketOpen.value = false },
    )
  }

  function disconnect() {
    handle?.close()
    handle = null
    socketOpen.value = false
    status.value = offline()
  }

  return { status, socketOpen, version, fetchHealth, connect, disconnect }
})