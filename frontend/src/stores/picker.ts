import { defineStore } from 'pinia'
import { ref } from 'vue'

import type { BinPosition } from './bins'

/**
 * 全局「回主页面点一个空格」的选择器。
 *
 * 用法：对话框里 await picker.request()，对话框在 active 期间让开，
 * 用户在网格上点空格 → confirm(pos)；点取消或按 Esc → cancel()。
 * 只认空格：点到有料的格子会给出提示，不会选中。
 */
export const usePickerStore = defineStore('picker', () => {
  const active = ref(false)
  const error = ref<string | null>(null)
  let resolver: ((pos: BinPosition | null) => void) | null = null

  function request(): Promise<BinPosition | null> {
    error.value = null
    active.value = true
    return new Promise((resolve) => { resolver = resolve })
  }

  function confirm(pos: BinPosition) {
    active.value = false
    error.value = null
    const done = resolver
    resolver = null
    done?.(pos)
  }

  function cancel() {
    active.value = false
    error.value = null
    const done = resolver
    resolver = null
    done?.(null)
  }

  /** 点到不能用的格子时给一句结论（如「该格已被占用」）。 */
  function warn(text: string) {
    error.value = text
  }

  return { active, error, request, confirm, cancel, warn }
})
