<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  Ban, Check, Combine, Crosshair, Move, Pencil, Plus, Trash2, TriangleAlert, X,
} from '@lucide/vue'

import type { ComponentItem } from '../api/types'
import {
  positionKey, useBinsStore, zoneGrid, zoneLayers, zoneName, type BinPosition,
} from '../stores/bins'
import { usePickerStore } from '../stores/picker'
import { useTheme } from '../stores/theme'
import BinCard from './BinCard.vue'
import GridDragPreview from './grid_drag_preview.vue'
import MotionPanel from './ui/motion_panel.vue'
import { use_grid_drag } from '../composables/use_grid_drag'
import { create_motion } from '../utils/motion'

const emit = defineEmits<{
  edit: [ComponentItem, BinPosition]
  create: [BinPosition]
}>()

const rootEl = ref<HTMLElement | null>(null)

// ---------- 批量选择模式 ----------
const operation_modes = [
  { key: 'move', label: '移动', exit: '退出移动', icon: Move },
  { key: 'merge', label: '合并格', exit: '退出合并', icon: Combine },
  { key: 'block', label: '停用格', exit: '退出停用', icon: Ban },
  { key: 'batch', label: '多选', exit: '退出多选', icon: Check },
] as const

/** One active tool owns grid input and the floating operation bar. */
type GridMode = typeof operation_modes[number]['key']

const active_mode = ref<GridMode | null>(null)
const operation_order = ['tools',
  ...operation_modes.map(mode => mode.key), 'picker', 'result']
const moveMode = computed(() => active_mode.value === 'move')
const mergeMode = computed(() => active_mode.value === 'merge')
const blockMode = computed(() => active_mode.value === 'block')
const batchMode = computed(() => active_mode.value === 'batch')

interface SelectedPosition {
  component_id: number
  pos: BinPosition
}
const selectedPositions = ref<Map<string, SelectedPosition>>(new Map())
const selectedIds = computed(() => new Set(
  [...selectedPositions.value.values()].map((item) => item.component_id),
))
const selectablePositions = computed<SelectedPosition[]>(() =>
  bins.components.flatMap((comp) => [comp, ...(comp.slots ?? [])].map((pos) => ({
    component_id: comp.id,
    pos: { zone: pos.zone, layer: pos.layer, slot: pos.slot },
  }))),
)
const confirmDelete = ref(false)
const deleteBusy = ref(false)
let confirmTimer: ReturnType<typeof setTimeout> | undefined

/**
 * @brief Change the single active tool and discard its transient selection.
 * @param next Tool to activate, or null to leave the operation workflow.
 */
function set_mode(next: GridMode | null) {
  if (mode_busy.value) return

  grid_drag.cancel()
  active_mode.value = next
  pickedId.value = null
  pickedSlot.value = null
  mergeSourceId.value = null
  selectedPositions.value = new Map()
  confirmDelete.value = false
  moveNote.value = null
  window.clearTimeout(confirmTimer)
  window.clearTimeout(noteTimer)
}

/** @brief The same entry selects, switches or exits an operation. */
function toggle_mode(next: GridMode) {
  if (picker.active) return

  set_mode(active_mode.value === next ? null : next)
}

function positionsInZone(zone: number): SelectedPosition[] {
  return selectablePositions.value.filter((item) => item.pos.zone === zone)
}

function zoneFullySelected(zone: number): boolean {
  const list = positionsInZone(zone)
  return list.length > 0 && list.every((item) =>
    selectedPositions.value.has(positionKey(item.pos)))
}

function selectZone(zone: number) {
  const next = new Map(selectedPositions.value)
  const list = positionsInZone(zone)
  if (zoneFullySelected(zone)) {
    for (const item of list) next.delete(positionKey(item.pos))
  } else {
    for (const item of list) next.set(positionKey(item.pos), item)
  }
  selectedPositions.value = next
}

function selectAll() {
  selectedPositions.value = new Map(selectablePositions.value.map((item) =>
    [positionKey(item.pos), item]))
}

function clearSelection() {
  selectedPositions.value = new Map()
}

function toggleSelect(comp: ComponentItem, pos: BinPosition) {
  const next = new Map(selectedPositions.value)
  const key = positionKey(pos)
  if (next.has(key)) next.delete(key)
  else next.set(key, { component_id: comp.id, pos })
  selectedPositions.value = next
}

// 区名就地编辑
const editingZone = ref(0)
const zoneDraft = ref('')

function startZoneEdit(zone: number) {
  editingZone.value = zone
  zoneDraft.value = bins.layout.zone_names?.[zone - 1] ?? ''
}

async function saveZoneEdit(zone: number) {
  try {
    await bins.updateZoneName(zone, zoneDraft.value)
  } finally {
    editingZone.value = 0
  }
}

function cancelZoneEdit() {
  editingZone.value = 0
}

function onCard(comp: ComponentItem, isShared = false, pos?: BinPosition) {
  if (picker.active) {
    picker.warn('该格已被占用')
    return
  }
  if (mode_busy.value || blockMode.value) return
  if (mergeMode.value) {
    void mergePickCard(comp, isShared, pos)
    return
  }
  if (batchMode.value) {
    toggleSelect(comp, pos ?? comp)
    return
  }
  if (moveMode.value) {
    if (isShared && pos) {
      toggleSlotPick(comp, pos)
      return
    }
    if (pickedSlot.value) return          // 手上拿着共用格时，点有料格子不做事
    if (picked.value && picked.value.id !== comp.id) void swapWith(comp)
    else pickCard(comp)
    return
  }
  emit('edit', comp, pos ?? comp)
}

async function deleteSelected() {
  if (deleteBusy.value) return
  if (!confirmDelete.value) {
    confirmDelete.value = true
    window.clearTimeout(confirmTimer)
    confirmTimer = window.setTimeout(() => { confirmDelete.value = false }, 3500)
    return
  }
  window.clearTimeout(confirmTimer)
  deleteBusy.value = true
  try {
    for (const item of selectedPositions.value.values()) {
      await bins.removePosition(item.component_id, item.pos)
    }
  } finally {
    await bins.refreshAll().catch(() => undefined)
    deleteBusy.value = false
    set_mode(null)
  }
}

const bins = useBinsStore()
const picker = usePickerStore()
const { mergeSlots: mergeView } = useTheme()
const locatedPrimaryId = ref<number | null>(null)
let primaryTimer: ReturnType<typeof setTimeout> | undefined

/** 定位元件当前的主格，仅调整页面滚动和高亮。 */
async function locatePrimary(id: number) {
  await nextTick()
  const target = rootEl.value?.querySelector<HTMLElement>(
    `[data-primary-component-id="${id}"]`,
  )
  if (!target) {
    flashNote('主格不在当前布局')
    return
  }
  locatedPrimaryId.value = id
  window.clearTimeout(primaryTimer)
  primaryTimer = window.setTimeout(() => {
    locatedPrimaryId.value = null
  }, 2500)
  target.scrollIntoView({
    behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches
      ? 'auto' : 'smooth',
    block: 'center',
  })
}

onBeforeUnmount(() => window.clearTimeout(primaryTimer))
defineExpose({ locatePrimary })

watch(() => bins.searchNavigationTick, async () => {
  await nextTick()
  const id = bins.currentSearchId
  if (id === null) return
  const target = rootEl.value?.querySelector<HTMLElement>(
    `[data-component-id="${id}"]`,
  ) ?? rootEl.value?.querySelector<HTMLElement>('[data-orphan-warning]')
  target?.scrollIntoView({
    behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches
      ? 'auto' : 'smooth',
    block: 'center',
  })
})

// ---------- 移动模式：点按拿起 → 点空格放下 ----------
const pickedId = ref<number | null>(null)
const moveNote = ref<string | null>(null)          // 搬家结果/提示
let noteTimer: ReturnType<typeof setTimeout> | undefined
const grid_drag = use_grid_drag(rootEl,
  computed(() => moveMode.value && !picker.active), flashNote)

const toolbar_slot = ref<HTMLElement | null>(null)
const toolbar_frame = ref<HTMLElement | null>(null)
const toolbar_width = ref<number | null>(null)
const toolbar_key = computed(() => picker.active ? 'picker'
  : active_mode.value ?? (moveNote.value ? 'result' : 'tools'))
const toolbar_motion = create_motion({ width: 0 }, values => {
  toolbar_width.value = values.width
})
let toolbar_observer: ResizeObserver | undefined
let toolbar_content_observer: MutationObserver | undefined

/** @brief Measure real controls and text, excluding flex-grow empty space. */
function toolbar_content_width(row: HTMLElement): number {
  const children = Array.from(row.children) as HTMLElement[]
  const gap = Number.parseFloat(getComputedStyle(row).columnGap) || 0

  return children.reduce((sum, child) => sum +
    (child.classList.contains('grid-toolbar-context')
      ? toolbar_content_width(child)
      : Math.max(child.offsetWidth, child.scrollWidth)), 0) +
    Math.max(0, children.length - 1) * gap
}

/** @brief Keep one right anchor while the toolbar changes its content. */
function measure_toolbar() {
  const frame = toolbar_frame.value
  const slot = toolbar_slot.value

  if (!frame || !slot) return

  const style = getComputedStyle(frame)
  const chrome = Number.parseFloat(style.paddingLeft) +
    Number.parseFloat(style.paddingRight) +
    Number.parseFloat(style.borderLeftWidth) +
    Number.parseFloat(style.borderRightWidth)
  const page = frame.querySelector(
    `[data-motion-page="${toolbar_key.value}"]`,
  )
  const row = page?.firstElementChild as HTMLElement | null

  if (!row) return

  const width = Math.min(slot.clientWidth,
    Math.ceil(toolbar_content_width(row) + chrome))

  toolbar_motion.set({ width }, toolbar_width.value === null)
}

watch(toolbar_key, async () => {
  await nextTick()
  measure_toolbar()
})

onMounted(() => {
  measure_toolbar()
  toolbar_observer = new ResizeObserver(measure_toolbar)
  if (toolbar_slot.value) toolbar_observer.observe(toolbar_slot.value)
  toolbar_content_observer = new MutationObserver(measure_toolbar)
  if (toolbar_frame.value) {
    toolbar_content_observer.observe(toolbar_frame.value, {
      subtree: true, childList: true, characterData: true,
    })
  }
})

onBeforeUnmount(() => {
  toolbar_observer?.disconnect()
  toolbar_content_observer?.disconnect()
  toolbar_motion.stop()
})


const picked = computed<ComponentItem | null>(
  () => bins.components.find((c) => c.id === pickedId.value) ?? null,
)

function flashNote(text: string) {
  moveNote.value = text
  window.clearTimeout(noteTimer)
  noteTimer = window.setTimeout(() => { moveNote.value = null }, 4500)
}

// 与操作流水、引导条一致的口径：区/层/格（格从 0 起）
function posText(pos: BinPosition): string {
  return `${pos.zone}区/${pos.layer}层/${pos.slot}格`
}

// 移动模式下点卡片：拿起 / 放回 / 与手上的互换
function pickCard(comp: ComponentItem) {
  if (pickedId.value === comp.id) {
    pickedId.value = null
    flashNote(`已把「${comp.name}」放回原处`)
    return
  }
  pickedId.value = comp.id
  pickedSlot.value = null
  moveNote.value = null
}

// 手上拿着一个，再点另一个有料的格子 -> 两个格子互换
async function swapWith(target: ComponentItem) {
  const held = picked.value

  if (!held || held.id === target.id) return

  pickedId.value = null
  await grid_drag.place(held, held, target)
}

/** @brief Click and keyboard placement use the same landing as pointer drag. */
async function placeAt(pos: BinPosition) {
  const shared = pickedSlot.value
  const component = shared
    ? bins.components.find(item => item.id === shared.compId) : picked.value

  if (!component) { flashNote('未拿起格子'); return }

  const from = shared?.pos ?? component

  pickedId.value = null
  pickedSlot.value = null
  await grid_drag.place(component, from, pos)
}

function onEmptyClick(pos: BinPosition) {
  if (picker.active) {          // 选格模式：点空格即选中并回到刚才的窗口
    picker.confirm(pos)
    return
  }
  if (mode_busy.value) return
  if (mergeMode.value) void mergeClickEmpty(pos)
  else if (moveMode.value) void placeAt(pos)
  else if (blockMode.value) void toggleBlockAt(pos)
  else if (!batchMode.value) emit('create', pos)
}

// ---------- 合并格模式：几个格子共用一个元件 ----------
const mergeSourceId = ref<number | null>(null)
const mergeBusy = ref(false)
const mergeSource = computed<ComponentItem | null>(
  () => bins.components.find((c) => c.id === mergeSourceId.value) ?? null,
)
// 移动模式拿着的是"要搬的卡"，合并模式拿着的是"主格"，视觉上都是这张卡被选中
const heldId = computed(() =>
  moveMode.value ? pickedId.value : mergeMode.value ? mergeSourceId.value : null)

// 移动模式下单独拿起的"共用格"（附加格）：它是一格，不是一个元件
const pickedSlot = ref<{ compId: number; pos: BinPosition } | null>(null)
watch(() => grid_drag.state.value, current => {
  if (!current) return
  pickedId.value = null
  pickedSlot.value = null
  moveNote.value = null
})

function isSlotHeld(cell: CellEntry): boolean {
  const held = pickedSlot.value
  return !!held && !!cell.comp && held.compId === cell.comp.id
    && positionKey(held.pos) === positionKey(cell.pos)
}

function toggleSlotPick(comp: ComponentItem, pos: BinPosition) {
  const held = pickedSlot.value
  if (held && held.compId === comp.id && positionKey(held.pos) === positionKey(pos)) {
    pickedSlot.value = null
    flashNote(`已放回 ${posText(pos)}`)
    return
  }
  pickedId.value = null
  moveNote.value = null
  pickedSlot.value = { compId: comp.id, pos }
}

// 先选主格，再点相同元件合并；点自己的共用卡解除那一格。
async function mergePickCard(comp: ComponentItem, isShared: boolean, pos?: BinPosition) {
  if (mergeBusy.value) return
  const src = mergeSource.value
  if (src && src.id !== comp.id) {
    mergeBusy.value = true
    try {
      const updated = await bins.mergeComponents(src.id, comp.id)
      const from = { zone: comp.zone, layer: comp.layer, slot: comp.slot }
      const to = { zone: src.zone, layer: src.layer, slot: src.slot }
      flashNote(`已把 ${posText(from)} 并入 ${posText(to)}，`
        + `数量合计 ${updated.quantity}`)
    } catch (e) {
      flashNote(`合并失败：${e instanceof Error ? e.message : String(e)}`)
    } finally {
      mergeBusy.value = false
    }
    return
  }
  if (isShared && pos) {
    mergeBusy.value = true
    try {
      await bins.removeSlot(comp.id, pos)
      flashNote(`已解除 ${posText(pos)}`)
    } catch (e) {
      flashNote(`解除失败：${e instanceof Error ? e.message : String(e)}`)
    } finally {
      mergeBusy.value = false
    }
    return
  }
  mergeSourceId.value = mergeSourceId.value === comp.id ? null : comp.id
  moveNote.value = null
}

async function mergeClickEmpty(pos: BinPosition) {
  if (mergeBusy.value) return
  const src = mergeSource.value
  if (!src) {
    flashNote('未选主格')
    return
  }
  mergeBusy.value = true
  try {
    await bins.addSlot(src.id, pos)
    flashNote(`已把 ${posText(pos)} 并入「${src.name}」`)
  } catch (e) {
    flashNote(`合并失败：${e instanceof Error ? e.message : String(e)}`)
  } finally {
    mergeBusy.value = false
  }
}

/** @brief Release a held selection before leaving its mode. */
function onEsc(ev: KeyboardEvent) {
  if (ev.key !== 'Escape' || ev.defaultPrevented) return
  if (picker.active) {
    picker.cancel()
    return
  }
  if (mode_busy.value) return
  if (mergeMode.value && mergeSourceId.value !== null) {
    mergeSourceId.value = null
    return
  }
  if (moveMode.value && pickedSlot.value) {
    const pos = pickedSlot.value.pos

    pickedSlot.value = null
    flashNote(`已放回 ${posText(pos)}`)
    return
  }
  if (moveMode.value && pickedId.value !== null) {
    const name = picked.value?.name ?? ''

    pickedId.value = null
    flashNote(`已把「${name}」放回原处`)
    return
  }
  set_mode(null)
}

onMounted(() => window.addEventListener('keydown', onEsc))
onBeforeUnmount(() => window.removeEventListener('keydown', onEsc))

// ---------- 停用格模式：把坏掉的格子标记为不可用 ----------
const block_busy = ref(false)
const mode_busy = computed(() => grid_drag.busy.value || mergeBusy.value ||
  block_busy.value || deleteBusy.value)

watch(() => picker.active, active => {
  if (active) set_mode(null)
})

onBeforeUnmount(() => {
  window.clearTimeout(confirmTimer)
  window.clearTimeout(noteTimer)
})

async function toggleBlockAt(pos: BinPosition) {
  if (block_busy.value) return

  block_busy.value = true

  const blocked = bins.blockedKeys.has(positionKey(pos))
  try {
    if (blocked) {
      await bins.unblockAt(pos)
      flashNote(`已恢复 ${posText(pos)} 可用`)
    } else {
      await bins.blockAt(pos)
      flashNote(`已标记 ${posText(pos)} 不可用`)
    }
  } catch (e) {
    flashNote(`操作失败：${e instanceof Error ? e.message : String(e)}`)
  } finally {
    block_busy.value = false
  }
}

interface CellEntry {
  key: string
  pos: BinPosition
  kind: 'card' | 'shared' | 'empty' | 'blocked'
  comp?: ComponentItem
  col: number
  row: number
  colSpan: number
  rowSpan: number
}

// 每个格子都按自己的行列显式摆位（跨格卡也不会把后面的格子挤错位）
function cellStyle(cell: CellEntry): Record<string, string> {
  return {
    gridColumn: `${cell.col + 1} / span ${cell.colSpan}`,
    gridRow: `${cell.row + 1} / span ${cell.rowSpan}`,
  }
}

// 一层的渲染列表：同一物料的占用格若能拼成一个完整矩形（横着、竖着、方块都行），
// 就合成一张跨格卡；拼不成矩形的仍是一格一张（主格卡片 + 其余共用卡）。
function layerCells(zone: number, layer: number): CellEntry[] {
  const [rows, cols] = zoneGrid(bins.layout, zone)
  const cells = rows * cols
  const owner = bins.slotOwner
  const out: CellEntry[] = []
  const eaten = new Set<number>()

  const ownerAt = (slot: number) => owner[positionKey({ zone, layer, slot })]
  const slotAt = (row: number, col: number) => row * cols + col

  // 1) 每个元件在本层占的格子
  const groups = new Map<number, { comp: ComponentItem; slots: number[] }>()
  for (let s = 0; s < cells; s++) {
    const info = ownerAt(s)
    if (!info) continue
    const item = groups.get(info.comp.id) ?? { comp: info.comp, slots: [] }
    item.slots.push(s)
    groups.set(info.comp.id, item)
  }

  // 2) 能拼成矩形的合成一张跨格卡
  if (mergeView.value && !mergeMode.value && !batchMode.value) {
    for (const { comp, slots } of groups.values()) {
      if (slots.length < 2) continue
      const r0 = Math.min(...slots.map((s) => Math.floor(s / cols)))
      const r1 = Math.max(...slots.map((s) => Math.floor(s / cols)))
      const c0 = Math.min(...slots.map((s) => s % cols))
      const c1 = Math.max(...slots.map((s) => s % cols))
      if ((r1 - r0 + 1) * (c1 - c0 + 1) !== slots.length) continue  // 有空缺就不合并
      for (let r = r0; r <= r1; r++) {
        for (let c = c0; c <= c1; c++) eaten.add(slotAt(r, c))
      }
      const primaryHere = comp.zone === zone && comp.layer === layer
      out.push({
        key: `c${zone}-${layer}-${r0}-${c0}`,
        pos: {
          zone, layer,
          slot: primaryHere ? comp.slot : slotAt(r0, c0),
        },
        kind: 'card', comp, row: r0, col: c0,
        colSpan: c1 - c0 + 1, rowSpan: r1 - r0 + 1,
      })
    }
  }

  // 3) 其余格子：主格出卡片、附加格出共用卡、空位出空位
  for (let s = 0; s < cells; s++) {
    if (eaten.has(s)) continue
    const row = Math.floor(s / cols)
    const col = s % cols
    const info = ownerAt(s)
    if (!info) {
      const pos = { zone, layer, slot: s }
      out.push({
        key: `e${zone}-${layer}-${s}`, pos,
        kind: bins.blockedKeys.has(positionKey(pos)) ? 'blocked' : 'empty',
        row, col, colSpan: 1, rowSpan: 1,
      })
      continue
    }
    out.push({
      key: `s${zone}-${layer}-${s}`, pos: { zone, layer, slot: s },
      kind: info.primary ? 'card' : 'shared', comp: info.comp,
      row, col, colSpan: 1, rowSpan: 1,
    })
  }
  return out
}

function zoneCols(zone: number): number {
  return zoneGrid(bins.layout, zone)[1]
}

async function fixOrphans() {
  try {
    const moved = await bins.relocateOrphans()
    bins.setQuery('')  // 搬完清空检索，避免旧高亮误导
    if (moved === 0) { /* 无空格可搬，下方仍会显示提示 */ }
  } catch {
    /* 提示由外部错误条展示 */
  }
}
</script>

<template>
  <div ref="rootEl" :data-grid-mode="active_mode ?? 'none'"
       class="fade-up mx-auto flex w-[min(1400px,calc(100%-24px))]
         flex-col gap-4 pb-16"
       :class="{ 'grid-drag-active': !!grid_drag.state.value }"
       @click.capture="grid_drag.capture_click">
    <GridDragPreview :controller="grid_drag" />
    <!-- One sticky surface owns both tool selection and active controls. -->
    <div ref="toolbar_slot" class="grid-toolbar-slot">
      <section ref="toolbar_frame" class="glass-panel grid-toolbar"
               :data-operation-mode="toolbar_key" aria-label="货架工具栏"
               :style="{ width: toolbar_width === null
                 ? 'max-content' : `${toolbar_width}px`,
                 borderColor: toolbar_key === 'tools' ? 'var(--line)'
                   : blockMode ? 'var(--warn)' : 'var(--accent)' }">
        <MotionPanel :active_key="toolbar_key" :page_order="operation_order">
        <template #default="{ page_key }">
          <nav v-if="page_key === 'tools'"
               class="grid-toolbar-menu" aria-label="货架操作模式">
            <button v-for="mode in operation_modes" :key="mode.key"
                    class="btn !py-1.5 text-xs" :disabled="mode_busy"
                    @click="toggle_mode(mode.key)">
              <component :is="mode.icon" :size="13" /> {{ mode.label }}
            </button>
          </nav>

          <div v-else class="grid-toolbar-page" role="group"
               aria-label="货架操作">
            <span class="flex shrink-0 items-center gap-2 text-[13px]
                         font-semibold">
              <component
                :is="operation_modes.find(mode => mode.key === page_key)?.icon
                  ?? (page_key === 'picker' ? Crosshair : Check)" :size="15"
                :style="{ color: page_key === 'block'
                  ? 'var(--warn)' : 'var(--accent)' }" />
              {{ operation_modes.find(mode => mode.key === page_key)?.label
                ?? (page_key === 'picker' ? '选格中' : '操作结果') }}
            </span>

            <div class="grid-toolbar-context">
              <template v-if="page_key === 'move'">
                <span class="chip shrink-0"
                      :data-drag-state="grid_drag.state.value?.phase
                        ?? 'ready'">
                  {{ grid_drag.busy.value ? '放置中' : '移动中' }}
                </span>
                <span v-if="grid_drag.state.value" class="truncate">
                  {{ grid_drag.state.value.component.name }}
                </span>
                <span v-else-if="picked" class="truncate">
                  {{ picked.name }} · {{ posText(picked) }}
                </span>
                <span v-else-if="pickedSlot" class="truncate">
                  共用格 {{ posText(pickedSlot.pos) }}
                </span>
                <span v-else style="color: var(--text-dim)">未选格子</span>
              </template>

              <template v-else-if="page_key === 'merge'">
                <template v-if="mergeSource">
                  <span class="truncate">
                    主格 {{ mergeSource.name }} · {{ posText(mergeSource) }}
                  </span>
                  <span class="chip num shrink-0">
                    共 {{ mergeSource.slot_count }} 格
                  </span>
                </template>
                <span v-else style="color: var(--text-dim)">未选主格</span>
              </template>

              <span v-else-if="page_key === 'block'" class="chip num shrink-0">
                已停用 {{ bins.blockedKeys.size }} 格
              </span>

              <template v-else-if="page_key === 'batch'">
                <span class="chip num shrink-0">
                  已选 {{ selectedPositions.size }} 格
                </span>
                <button class="btn shrink-0 !py-1.5 text-xs"
                        :disabled="mode_busy" @click="selectAll">全选</button>
                <button class="btn shrink-0 !py-1.5 text-xs"
                        :disabled="mode_busy || selectedIds.size === 0"
                        @click="clearSelection">清空选择</button>
                <button class="btn btn-danger shrink-0 !py-1.5 text-xs"
                        :disabled="mode_busy || selectedIds.size === 0"
                        @click="deleteSelected">
                  <Trash2 :size="13" />
                  {{ confirmDelete ? '确认删除？' : '删除所选' }}
                </button>
              </template>

              <span v-if="page_key === 'picker' && picker.error"
                    class="truncate" style="color: var(--danger)">
                {{ picker.error }}
              </span>
              <span v-else-if="moveNote" class="truncate"
                    style="color: var(--success)">{{ moveNote }}</span>
            </div>

            <span v-if="mode_busy" class="chip shrink-0">处理中</span>
            <button class="btn btn-ghost shrink-0 !py-1.5 text-xs"
                    :disabled="mode_busy"
                    @click="page_key === 'picker'
                      ? picker.cancel() : set_mode(null)">
              {{ operation_modes.find(mode => mode.key === page_key)?.exit
                ?? (page_key === 'picker' ? '取消' : '关闭') }}
            </button>
          </div>
        </template>
        </MotionPanel>
      </section>
    </div>

    <!-- 游离元件提示：布局缩容后超出网格 -->
    <div
      v-if="bins.orphanComps.length > 0"
      data-orphan-warning
      class="glass-panel flex flex-wrap items-center gap-3 rounded-2xl px-4 py-3"
      style="border-color: color-mix(in srgb, var(--warn) 55%, var(--line))"
    >
      <TriangleAlert :size="18" style="color: var(--warn)" />
      <span class="text-[13px] font-semibold">
        {{ bins.orphanComps.length }} 个元件超出当前网格
      </span>
      <span class="chip" v-for="c in bins.orphanComps.slice(0, 6)" :key="c.id">
        {{ c.name }}
      </span>
      <span v-if="bins.orphanComps.length > 6" class="text-xs" style="color: var(--text-faint)">
        等 {{ bins.orphanComps.length }} 个
      </span>
      <button class="btn btn-primary ml-auto !py-1.5 text-xs" @click="fixOrphans">
        <Plus :size="14" /> 自动搬入空格
      </button>
    </div>

    <div v-if="bins.loading && !bins.components.length" class="py-20 text-center" style="color: var(--text-faint)">
      载入货架…
    </div>

    <!-- 分区为组：区内层数纵向堆叠，每层一个 row×col 网格 -->
    <section
      v-for="zone in bins.layout.zone_count"
      :key="zone"
      class="glass-panel shelf-reveal rounded-3xl p-4 sm:p-6"
      :style="{ '--shelf-delay': Math.min(zone - 1, 4) * 45 + 'ms' }"
    >
      <div class="mb-4 flex items-end gap-3">
        <div class="flex flex-col">
          <div v-if="editingZone === zone" class="flex items-center gap-1.5">
            <input v-model="zoneDraft" class="input !py-1.5 text-lg font-extrabold" maxlength="24"
                   :placeholder="'第 ' + zone + ' 区'" autofocus
                   @keydown.enter="saveZoneEdit(zone)" @keydown.esc="cancelZoneEdit" />
            <button class="icon-btn !h-8 !w-8" title="保存区名" @click="saveZoneEdit(zone)"><Check :size="15" /></button>
            <button class="icon-btn !h-8 !w-8" title="取消" @click="cancelZoneEdit"><X :size="15" /></button>
          </div>
          <div v-else class="group flex items-center gap-1.5">
            <h2 class="text-xl font-extrabold tracking-[0.12em]">
              {{ zoneName(bins.layout, zone) }}
            </h2>
            <button class="icon-btn !h-7 !w-7 opacity-0 transition-opacity group-hover:opacity-100"
                    title="修改区名" @click="startZoneEdit(zone)">
              <Pencil :size="13" />
            </button>
          </div>
        </div>
        <div class="mb-0.5 flex items-center gap-1.5">
          <button v-if="batchMode" class="btn !px-2.5 !py-1 text-[11px]"
                  @click="selectZone(zone)">
            {{ zoneFullySelected(zone) ? '取消本区' : '选本区' }}
          </button>
          <span class="chip !text-[10.5px]">共 {{ zoneLayers(bins.layout, zone) }} 层</span>
          <span class="chip !text-[10.5px] num">
            每层 {{ zoneGrid(bins.layout, zone)[0] }}×{{ zoneGrid(bins.layout, zone)[1] }} 格
          </span>
        </div>
      </div>

      <div class="flex flex-col gap-6">
        <div v-for="layer in zoneLayers(bins.layout, zone)" :key="layer">
          <div class="mb-2 flex items-center gap-2">
            <span class="mono text-[11px] font-bold tracking-[0.1em]" style="color: var(--text-faint)">
              层 {{ layer }}
            </span>
            <div class="h-px flex-1" style="background: var(--line)" />
          </div>

          <div class="overflow-x-auto px-1 pt-2.5 pb-2">
          <TransitionGroup name="cell" tag="div" appear
            class="grid gap-2.5"
            :style="{ gridTemplateColumns: 'repeat(' + zoneCols(zone) + ', minmax(118px, 1fr))' }"
          >
            <template v-for="cell in layerCells(zone, layer)"
                      :key="cell.key + ':' + (cell.comp?.id ?? cell.kind)">
              <!-- 有料格子：可能是跨格大卡，也可能是附加格的共用卡 -->
              <BinCard
                v-if="cell.kind === 'card' || cell.kind === 'shared'"
                :comp="cell.comp!"
                v-bind="grid_drag.attributes(cell)"
                :class="grid_drag.classes(cell)"
                @pointerdown="grid_drag.start($event, cell)"
                :grid-style="cellStyle(cell)"
                :col-span="cell.colSpan"
                :row-span="cell.rowSpan"
                :shared="cell.kind === 'shared'"
                :primary="positionKey(cell.pos) === positionKey(cell.comp!)"
                :dimmed="!!bins.matchedIds && !bins.matchedIds.has(cell.comp!.id)"
                :current="bins.currentSearchId === cell.comp!.id"
                :flashing="!!bins.flashKeys[positionKey(cell.pos)]
                  || (locatedPrimaryId === cell.comp!.id
                    && positionKey(cell.pos) === positionKey(cell.comp!))"
                :guide="bins.guideKey === positionKey(cell.pos)"
                :selectable="batchMode"
                :selected="batchMode && selectedPositions.has(positionKey(cell.pos))"
                :show-supplier="batchMode"
                :picked="cell.kind === 'shared' ? isSlotHeld(cell) : heldId === cell.comp!.id"
                :swap-ready="!pickedSlot && !!picked && pickedId !== cell.comp!.id"
                @click="onCard($event, cell.kind === 'shared', cell.pos)"
                @locate-primary="locatePrimary"
              />
              <!-- 不可用格：坏掉的格子，任何模式都不会往里放东西 -->
              <div
                v-else-if="cell.kind === 'blocked'"
                v-bind="grid_drag.attributes(cell)"
                class="card-blocked grid min-h-[96px] cursor-pointer place-items-center rounded-[14px]"
                :style="cellStyle(cell)"
                :class="{
                  'blocked-active': blockMode,
                  'card-dimmed': bins.matchedIds !== null,
                  ...grid_drag.classes(cell),
                }"
                :title="blockMode ? '恢复可用' : '不可用'"
                @click="blockMode && toggleBlockAt(cell.pos)"
              >
                <Ban :size="18" />
              </div>
              <!-- 空位：虚线占位卡，点击新建 -->
              <button
                v-else
                v-bind="grid_drag.attributes(cell)"
                class="card-empty grid min-h-[96px] place-items-center rounded-[14px]"
                :style="cellStyle(cell)"
                :class="{
                  'move-ready': !!heldId || !!pickedSlot || picker.active,
                  ...grid_drag.classes(cell) }"
                :title="picker.active || heldId || pickedSlot ? '选它' : '空位'"
                @click="onEmptyClick(cell.pos)"
              >
                <Plus :size="20" />
              </button>
            </template>
          </TransitionGroup>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>
