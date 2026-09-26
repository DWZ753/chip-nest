// 元件货架主数据：布局 + 元件 + 检索 + 高亮/引导目标
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { api, ApiError } from '../api/client'
import type { ComponentItem, LayoutConfig } from '../api/types'

const DEFAULT_LAYOUT: LayoutConfig = {
  zone_count: 1, layer_count: 3, row_count: 1, col_count: 4,
  zone_names: [], zone_sizes: [], zone_layers: [], blocked: [], updated_at: '',
}

export interface BinPosition { zone: number; layer: number; slot: number }
type SearchOption = 'matchCase' | 'wholeWord' | 'useRegex'

const COMPONENT_PAGE_SIZE = 5000

// 区显示名：自定义名优先，否则「第N区」
// 某区的 [行, 列]：优先 zone_sizes，缺项用全局默认
export function zoneGrid(layout: LayoutConfig, zone: number): [number, number] {
  const item = layout.zone_sizes?.[zone - 1]
  if (Array.isArray(item) && item.length === 2) return [item[0], item[1]]
  return [layout.row_count, layout.col_count]
}

// 某区的层数：优先 zone_layers，缺项用全局默认 layer_count
export function zoneLayers(layout: LayoutConfig, zone: number): number {
  const n = layout.zone_layers?.[zone - 1]
  return Number.isFinite(n) && (n as number) >= 1 ? (n as number) : layout.layer_count
}

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
  const searchOptions = ref({ matchCase: false, wholeWord: false, useRegex: false })
  const searchError = ref<string | null>(null)
  // 检索命中的元件 id（null=没有检索）：命中的高亮，没命中的在网格里变暗但**不消失**
  const matchedIds = ref<Set<number> | null>(null)
  const searchHitIds = ref<number[]>([])
  const currentSearchIndex = ref(-1)
  const searchNavigationTick = ref(0)
  const currentSearchId = computed(() =>
    searchHitIds.value[currentSearchIndex.value] ?? null)
  // 检索命中闪烁集合（key -> 无需时间戳，1.6s 后清除使动画结束）
  const flashKeys = ref<Record<string, true>>({})
  // 当前布局下所有空位（按 区→层→格 顺序；供购买清单逐项放置用）
  // 被标记为不可用的格子（物理容器坏了等）
  const blockedKeys = computed<Set<string>>(
    () => new Set((layout.value.blocked ?? []).map((b) => positionKey(b))),
  )

  function freeSlots(): BinPosition[] {
    // 主格、附加格、不可用格都不算空位
    const occupied = new Set(components.value.map(positionKey))
    for (const c of components.value) {
      for (const s of c.slots ?? []) occupied.add(positionKey(s))
    }
    for (const key of blockedKeys.value) occupied.add(key)
    const out: BinPosition[] = []
    for (let z = 1; z <= layout.value.zone_count; z++) {
      const [rows, cols] = zoneGrid(layout.value, z)
      for (let l = 1; l <= zoneLayers(layout.value, z); l++) {
        for (let s = 0; s < rows * cols; s++) {
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
  let queryRevision = 0
  let guideLedQueue = Promise.resolve()

  const compsByKey = computed<Record<string, ComponentItem>>(() => {
    const map: Record<string, ComponentItem> = {}
    for (const c of components.value) map[positionKey(c)] = c
    return map
  })

  // 位置 -> 占着它的元件（primary=true 是主格，false 是附加格）
  const slotOwner = computed<Record<string, { comp: ComponentItem; primary: boolean }>>(() => {
    const map: Record<string, { comp: ComponentItem; primary: boolean }> = {}
    for (const c of components.value) {
      map[positionKey(c)] = { comp: c, primary: true }
      for (const s of c.slots ?? []) map[positionKey(s)] = { comp: c, primary: false }
    }
    return map
  })

  function posInLayout(pos: BinPosition): boolean {
    if (pos.zone > layout.value.zone_count) return false
    if (pos.layer > zoneLayers(layout.value, pos.zone)) return false
    const [rows, cols] = zoneGrid(layout.value, pos.zone)
    return pos.slot >= 0 && pos.slot < rows * cols
  }

  // 布局缩容后的游离元件：主格或任一附加格超出网格都算
  const orphanComps = computed<ComponentItem[]>(() => {
    return components.value
      .filter((c) => !posInLayout(c) || (c.slots ?? []).some((s) => !posInLayout(s)))
      .sort((a, b) => a.zone - b.zone || a.layer - b.layer || a.slot - b.slot)
  })

  // 上一次触发过呼吸动画的查询串：避免同查询反复重启动画造成卡顿
  let lastFlashQuery = ''
  const FLASH_MS = 2000

  function addFlash(keys: string[], forQuery: string) {
    if (!forQuery || forQuery === lastFlashQuery) return
    lastFlashQuery = forQuery
    for (const k of keys) flashKeys.value[k] = true
    window.clearTimeout(flashTimer)
    flashTimer = window.setTimeout(() => {
      flashKeys.value = {}
    }, FLASH_MS)
  }

  async function refreshLayout() {
    layout.value = await api.getLayout()
  }

  async function refreshComponents() {
    loading.value = true
    error.value = null
    try {
      // 永远拉全量：检索只用来标记命中，格子上的东西不能因为检索而消失
      components.value = await loadAllComponents()
      await applyQuery()
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
      throw e
    } finally {
      loading.value = false
    }
  }

  // 就地修改区名（无需进仓库布局）
  async function updateZoneName(zone: number, name: string) {
    const names = Array.from({ length: layout.value.zone_count }, (_, i) =>
      (layout.value.zone_names?.[i] ?? '').slice(0, 24))
    names[zone - 1] = name.trim().slice(0, 24)
    const saved = await api.putLayout({
      zone_count: layout.value.zone_count,
      layer_count: layout.value.layer_count,
      row_count: layout.value.row_count,
      col_count: layout.value.col_count,
      zone_names: names,
      zone_sizes: layout.value.zone_sizes ?? [],
      zone_layers: layout.value.zone_layers ?? [],
    })
    layout.value = saved
  }

  async function refreshAll() {
    await Promise.all([refreshLayout(), refreshComponents()])
  }

  // 只重算"哪些命中"，不动元件列表；命中卡片呼吸高亮一次
  async function applyQuery() {
    const revision = ++queryRevision
    const q = query.value.trim()
    if (!q) {
      matchedIds.value = null
      searchHitIds.value = []
      currentSearchIndex.value = -1
      searchError.value = null
      return
    }
    try {
      const options = searchOptions.value
      const hits = await api.searchComponents({
        q,
        match_case: options.matchCase,
        whole_word: options.wholeWord,
        use_regex: options.useRegex,
      })
      if (revision !== queryRevision) return
      const hitSet = new Set(hits.ids)
      matchedIds.value = hitSet
      searchHitIds.value = hits.ids
      currentSearchIndex.value = -1
      searchError.value = null
      addFlash(components.value.filter((c) => hitSet.has(c.id))
        .map(positionKey), JSON.stringify([q, options]))
    } catch (e) {
      if (revision !== queryRevision) return
      matchedIds.value = null
      searchHitIds.value = []
      currentSearchIndex.value = -1
      searchError.value = e instanceof ApiError && e.status === 422
        ? '正则表达式无效' : '搜索失败'
    }
  }

  async function loadAllComponents(
    opts: {
      q?: string; zone?: number; layer?: number
      match_case?: boolean; whole_word?: boolean; use_regex?: boolean
    } = {},
  ): Promise<ComponentItem[]> {
    const all: ComponentItem[] = []
    let offset = 0

    while (true) {
      const page = await api.listComponents({
        ...opts, limit: COMPONENT_PAGE_SIZE, offset,
      })
      all.push(...page)
      if (page.length < COMPONENT_PAGE_SIZE) return all
      offset += COMPONENT_PAGE_SIZE
    }
  }

  function setQuery(q: string) {
    query.value = q
    scheduleQuery()
  }

  function toggleSearchOption(option: SearchOption) {
    searchOptions.value[option] = !searchOptions.value[option]
    scheduleQuery()
  }

  function navigateSearch(direction: -1 | 1) {
    const count = searchHitIds.value.length
    if (!count) return
    if (currentSearchIndex.value < 0) {
      currentSearchIndex.value = direction > 0 ? 0 : count - 1
      searchNavigationTick.value++
      return
    }
    currentSearchIndex.value = (currentSearchIndex.value + direction + count) % count
    searchNavigationTick.value++
  }

  function scheduleQuery() {
    queryRevision++
    searchError.value = null
    matchedIds.value = null
    searchHitIds.value = []
    currentSearchIndex.value = -1
    window.clearTimeout(queryTimer)
    if (!query.value.trim()) {
      lastFlashQuery = ''
      return
    }
    queryTimer = window.setTimeout(() => {
      void applyQuery()
    }, 320)
  }

  function upsert(comp: ComponentItem) {
    const i = components.value.findIndex((c) => c.id === comp.id)
    if (i >= 0) components.value[i] = comp
    else components.value.push(comp)
  }

  // 拖动搬家：PATCH 三字段成组；目标被占后端返回 409（错误信息原样抛出）
  async function moveComponent(id: number, pos: BinPosition) {
    const comp = components.value.find((c) => c.id === id)
    if (comp && comp.zone === pos.zone && comp.layer === pos.layer && comp.slot === pos.slot) {
      return comp
    }
    const updated = await api.patchComponent(id, {
      zone: pos.zone, layer: pos.layer, slot: pos.slot,
    })
    upsert(updated)
    return updated
  }

  // 不可用格：标记 / 恢复（物理容器坏了就标上，任何地方都不会再往里放东西）
  async function blockAt(pos: BinPosition) {
    await api.blockSlot(pos)
    await refreshLayout()
  }

  async function unblockAt(pos: BinPosition) {
    await api.unblockSlot(pos)
    await refreshLayout()
  }

  // 撤销上一步：后端按快照还原，这边整体刷新
  async function undoLast() {
    const result = await api.undoLast()
    if (result.ok) await refreshAll()
    return result
  }

  // 多格存放：加/减一个占用格（库存不变，只是一个物料放在多处）
  async function addSlot(id: number, pos: BinPosition) {
    const updated = await api.addComponentSlot(id, pos)
    upsert(updated)
    return updated
  }

  async function removeSlot(id: number, pos: BinPosition) {
    const updated = await api.removeComponentSlot(id, pos)
    upsert(updated)
    return updated
  }

  // 两个格子互换内容：后端一条事务完成，这里把两个元件都刷新到本地
  async function swapComponents(aId: number, bId: number) {
    const result = await api.swapComponents(aId, bId)
    upsert(result.a)
    upsert(result.b)
    return result
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
    for (const c of components.value) {
      for (const s of c.slots ?? []) occupied.add(positionKey(s))
    }
    let moved = 0
    // 附加格越界：拆掉再挂到新空位（元件本身不动）
    for (const comp of orphanComps.value) {
      for (const extra of [...(comp.slots ?? [])]) {
        if (posInLayout(extra)) continue
        let target: BinPosition | null = null
        for (let z = 1; z <= layout.value.zone_count && !target; z++) {
          const [rows, cols] = zoneGrid(layout.value, z)
          for (let l = 1; l <= zoneLayers(layout.value, z) && !target; l++) {
            for (let s = 0; s < rows * cols; s++) {
              const pos = { zone: z, layer: l, slot: s }
              if (!occupied.has(positionKey(pos))) { target = pos; break }
            }
          }
        }
        if (!target) break
        await removeSlot(comp.id, extra)
        await addSlot(comp.id, target)
        occupied.add(positionKey(target))
        moved++
      }
    }
    for (const orphan of orphanComps.value) {
      if (posInLayout(orphan)) continue
      let target: BinPosition | null = null
      for (let z = 1; z <= layout.value.zone_count && !target; z++) {
        const [rows, cols] = zoneGrid(layout.value, z)
        for (let l = 1; l <= zoneLayers(layout.value, z) && !target; l++) {
          for (let s = 0; s < rows * cols; s++) {
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

  // 清空数据后：清掉检索词/高亮/引导，并把布局与元件整体重拉
  async function resetAfterWipe() {
    query.value = ''
    queryRevision++
    searchError.value = null
    lastFlashQuery = ''
    matchedIds.value = null
    searchHitIds.value = []
    currentSearchIndex.value = -1
    window.clearTimeout(queryTimer)
    flashKeys.value = {}
    guideKey.value = null
    await refreshAll()
  }

  // ---- BOM 引导联动 ----
  function setGuidePosition(pos: BinPosition | null) {
    const key = pos ? positionKey(pos) : null
    guideKey.value = key
    const componentId = key ? compsByKey.value[key]?.id ?? null : null
    guideLedQueue = guideLedQueue
      .then(() => api.setGuideLed(componentId))
      .then(() => undefined)
      .catch(() => undefined)
  }

  return {
    layout, components, loading, error, query, searchOptions, searchError,
    matchedIds, searchHitIds, currentSearchIndex, currentSearchId,
    searchNavigationTick,
    flashKeys, guideKey,
    compsByKey, orphanComps,
    refreshLayout, refreshComponents, refreshAll, setQuery, toggleSearchOption,
    navigateSearch,
    freeSlots, upsert,
    updateZoneName,
    moveComponent, swapComponents, addSlot, removeSlot, blockAt, unblockAt, undoLast,
    removeComponent, adjustStock, relocateOrphans, setGuidePosition, slotOwner,
    posInLayout, blockedKeys,
    resetAfterWipe,
  }
})
