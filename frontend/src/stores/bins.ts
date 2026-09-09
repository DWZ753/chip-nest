// 元件货架主数据：布局 + 元件 + 检索 + 高亮/引导目标
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { api } from '../api/client'
import type { ComponentItem, LayoutConfig } from '../api/types'

const DEFAULT_LAYOUT: LayoutConfig = {
  zone_count: 1, layer_count: 3, row_count: 1, col_count: 4,
  zone_names: [], updated_at: '',
}

export interface BinPosition { zone: number; layer: number; slot: number }

// 区显示名：自定义名优先，否则「第N区」
export function zoneName(layout: LayoutConfig, zone: number): string {
  const n = layout.zone_names?.[zone - 1]?.trim()
  return n || `第 ${zone} 区`
}

export const positionKey = (p: BinPosition): string =>
  `${p.zone}:${p.layer}:${p.slot}`

export const useBinsStore = defineStore('bins', () => {
  const layout = ref<LayoutConfig>({ ...DEFAULT_LAYOUT })
  const components = ref<ComponentItem[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  const query = ref('')
  // 检索命中闪烁集合（key -> 无需时间戳，1.6s 后清除使动画结束）
  const flashKeys = ref<Record<string, true>>({})
  // 当前布局下所有空位（按 区→层→格 顺序；供购买清单逐项放置用）
  function freeSlots(): BinPosition[] {
    const occupied = new Set(components.value.map(positionKey))
    const out: BinPosition[] = []
    for (let z = 1; z <= layout.value.zone_count; z++) {
      for (let l = 1; l <= layout.value.layer_count; l++) {
        for (let s = 0; s < layout.value.row_count * layout.value.col_count; s++) {
          const pos = { zone: z, layer: l, slot: s }
          if (!occupied.has(positionKey(pos))) out.push(pos)
        }
      }
    }
    return out
  }

  // BOM 引导当前步对应格子（GuideOverlay 点亮 + 卡片描边）
  const guideKey = ref<string | null>(null)

  let flashTimer: ReturnType<typeof setTimeout> | undefined
  let queryTimer: ReturnType<typeof setTimeout> | undefined

  const compsByKey = computed<Record<string, ComponentItem>>(() => {
    const map: Record<string, ComponentItem> = {}
    for (const c of components.value) map[positionKey(c)] = c
    return map
  })

  // 布局缩容后的游离元件（超出区/层/格范围）
  const orphanComps = computed<ComponentItem[]>(() => {
    const cells = layout.value.row_count * layout.value.col_count
    return components.value
      .filter((c) => c.zone > layout.value.zone_count
        || c.layer > layout.value.layer_count
        || c.slot >= cells)
      .sort((a, b) => a.zone - b.zone || a.layer - b.layer || a.slot - b.slot)
  })

  function addFlash(keys: string[]) {
    for (const k of keys) flashKeys.value[k] = true
    window.clearTimeout(flashTimer)
    flashTimer = window.setTimeout(() => {
      flashKeys.value = {}
    }, 1700)
  }

  async function refreshLayout() {
    layout.value = await api.getLayout()
  }

  async function refreshComponents() {
    loading.value = true
    error.value = null
    try {
      const rows = await api.listComponents({ q: query.value })
      components.value = rows
      // 命中检索的行整体呼吸上浮一次
      if (query.value.trim()) addFlash(rows.map(positionKey))
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
      throw e
    } finally {
      loading.value = false
    }
  }

  async function refreshAll() {
    await Promise.all([refreshLayout(), refreshComponents()])
  }

  function setQuery(q: string) {
    query.value = q
    window.clearTimeout(queryTimer)
    queryTimer = window.setTimeout(() => {
      void refreshComponents().catch(() => undefined)
    }, 220)
  }

  function upsert(comp: ComponentItem) {
    const i = components.value.findIndex((c) => c.id === comp.id)
    if (i >= 0) components.value[i] = comp
    else components.value.push(comp)
  }

  async function removeComponent(id: number) {
    await api.deleteComponent(id)
    components.value = components.value.filter((c) => c.id !== id)
  }

  async function adjustStock(id: number, delta: number, note?: string) {
    const comp = await api.changeStock(id, delta, note)
    upsert(comp)
    return comp
  }

  // 布局缩容后一键把游离元件搬进空格（从 1区/1层/0格 起顺序填）
  async function relocateOrphans(): Promise<number> {
    const occupied = new Set(components.value.map(positionKey))
    let moved = 0
    for (const orphan of orphanComps.value) {
      let target: BinPosition | null = null
      for (let z = 1; z <= layout.value.zone_count && !target; z++) {
        for (let l = 1; l <= layout.value.layer_count && !target; l++) {
          for (let s = 0; s < layout.value.row_count * layout.value.col_count; s++) {
            const pos = { zone: z, layer: l, slot: s }
            if (!occupied.has(positionKey(pos))) { target = pos; break }
          }
        }
      }
      if (!target) break
      const updated = await api.patchComponent(orphan.id, { ...target })
      upsert(updated)
      occupied.add(positionKey(target))
      moved++
    }
    await refreshComponents()
    return moved
  }

  // ---- BOM 引导联动 ----
  function setGuidePosition(pos: BinPosition | null) {
    guideKey.value = pos ? positionKey(pos) : null
  }

  return {
    layout, components, loading, error, query, flashKeys, guideKey,
    compsByKey, orphanComps,
    refreshLayout, refreshComponents, refreshAll, setQuery, freeSlots, upsert,
    removeComponent, adjustStock, relocateOrphans, setGuidePosition,
  }
})