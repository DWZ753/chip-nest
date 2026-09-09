<script setup lang="ts">
import { computed } from 'vue'

import { useConnectionStore } from '../stores/connection'

const connection = useConnectionStore()

// 徽标三态：串口 青 / 模拟 琥珀实心 / 离线 红
const badge = computed(() => {
  const s = connection.status
  if (!connection.socketOpen || !s.connected) return 'conn-off'
  return s.mode === 'serial' ? 'conn-serial' : 'conn-mock'
})

const dotCls = computed(() => {
  if (!connection.socketOpen || !connection.status.connected) return 'dot-err'
  return connection.status.mode === 'serial' ? 'dot-ok' : 'dot-warn'
})

const text = computed(() => {
  const s = connection.status
  if (!connection.socketOpen) return '离线'
  if (!s.connected) return '断开'
  return s.mode === 'serial' ? '串口' : '模拟'
})

const label = computed(() => {
  const s = connection.status
  if (!connection.socketOpen) return '后端未连接'
  if (!s.connected) return '适配器断开'
  return s.mode === 'serial'
    ? `串口已连接：${s.device ?? ''}`
    : '模拟模式（无 ESP32）'
})
</script>

<template>
  <span class="conn-badge" :class="badge" :title="label">
    <span class="status-dot" :class="dotCls" />
    {{ text }}
  </span>
</template>