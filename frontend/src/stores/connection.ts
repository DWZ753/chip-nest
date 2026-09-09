// HAL 连接状态：WebSocket 推送 + 失败降级红点
import { defineStore } from 'pinia'
import { ref } from 'vue'

import { openStatusSocket, type StatusSocketHandle } from '../api/ws'
import type { AdapterStatus } from '../api/types'

function offline(): AdapterStatus {
  return { mode: 'mock', connected: false, device: null, error: '未连接到后端' }
}

export const useConnectionStore = defineStore('connection', () => {
  const status = ref<AdapterStatus>(offline())
  const socketOpen = ref(false)
  let handle: StatusSocketHandle | null = null

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

  return { status, socketOpen, connect, disconnect }
})
