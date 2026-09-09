// /api/v1/ws/status WebSocket 封装：自动重连 + 最新状态去抖
import type { AdapterStatus, WsStatusMessage } from './types'

const PROTO = location.protocol === 'https:' ? 'wss:' : 'ws:'
const URL = `${PROTO}//${location.host}/api/v1/ws/status`

export interface StatusSocketHandle {
  close: () => void
}

export function openStatusSocket(
  onStatus: (status: AdapterStatus) => void,
  onDown: () => void,
): StatusSocketHandle {
  let ws: WebSocket | null = null
  let closed = false
  let timer: number | undefined

  const schedule = (delayMs: number) => {
    if (closed) return
    window.clearTimeout(timer)
    timer = window.setTimeout(connect, delayMs)
  }

  function connect() {
    if (closed) return
    try {
      ws = new WebSocket(URL)
    } catch {
      onDown()
      schedule(2000)
      return
    }
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(String(ev.data)) as WsStatusMessage
        if (msg.type === 'adapter.status') {
          onStatus({ mode: msg.mode, connected: msg.connected,
                     device: msg.device, error: msg.error })
        }
      } catch { /* 忽略坏帧 */ }
    }
    ws.onclose = () => {
      onDown()
      schedule(1500)
    }
    ws.onerror = () => { /* onclose 会触发重连 */ }
  }

  connect()
  return {
    close: () => {
      closed = true
      window.clearTimeout(timer)
      ws?.close()
    },
  }
}
