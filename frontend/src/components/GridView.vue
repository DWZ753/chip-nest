<script setup lang="ts">
import { ref } from 'vue'
import { Check, Move, Pencil, Plus, Trash2, TriangleAlert, X } from '@lucide/vue'

import { api } from '../api/client'
import type { ComponentItem } from '../api/types'
import { positionKey, useBinsStore, zoneGrid, zoneName, type BinPosition } from '../stores/bins'
import BinCard from './BinCard.vue'

const emit = defineEmits<{
  edit: [ComponentItem]
  create: [BinPosition]
}>()

// ---------- 批量选择模式 ----------
const batchMode = ref(false)
const selectedIds = ref<Set<number>>(new Set())
const confirmDelete = ref(false)
let confirmTimer: ReturnType<typeof setTimeout> | undefined

function enterBatch() {
  batchMode.value = true
  selectedIds.value = new Set()
}

function exitBatch() {
  batchMode.value = false
  selectedIds.value = new Set()
  confirmDelete.value = false
  window.clearTimeout(confirmTimer)
}

function compsInZone(zone: number): ComponentItem[] {
  return bins.components.filter((c) => c.zone === zone)
}

function zoneFullySelected(zone: number): boolean {
  const list = compsInZone(zone)
  return list.length > 0 && list.every((c) => selectedIds.value.has(c.id))
}

function selectZone(zone: number) {
  const next = new Set(selectedIds.value)
  const list = compsInZone(zone)
  if (zoneFullySelected(zone)) {
    for (const c of list) next.delete(c.id)
  } else {
    for (const c of list) next.add(c.id)
  }
  selectedIds.value = next
}

function selectAll() {
  selectedIds.value = new Set(bins.components.map((c) => c.id))
}

function clearSelection() {
  selectedIds.value = new Set()
}

function toggleSelect(comp: ComponentItem) {
  const next = new Set(selectedIds.value)
  if (next.has(comp.id)) next.delete(comp.id)
  else next.add(comp.id)
  selectedIds.value = next
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

function onCard(comp: ComponentItem) {
  if (batchMode.value) toggleSelect(comp)
  else emit('edit', comp)
}

const confirmClearSupplier = ref(false)
let clearTimer: ReturnType<typeof setTimeout> | undefined

async function clearSupplierParts() {
  if (!confirmClearSupplier.value) {
    confirmClearSupplier.value = true
    window.clearTimeout(clearTimer)
    clearTimer = window.setTimeout(() => { confirmClearSupplier.value = false }, 3500)
    return
  }
  window.clearTimeout(clearTimer)
  for (const id of selectedIds.value) {
    const updated = await api.patchComponent(id, { supplier_part: '' })
    bins.upsert(updated)          // 立即更新本地状态
  }
  confirmClearSupplier.value = false
  await bins.refreshAll()         // 再与后端对齐一次
  exitBatch()
}

async function deleteSelected() {
  if (!confirmDelete.value) {
    confirmDelete.value = true
    window.clearTimeout(confirmTimer)
    confirmTimer = window.setTimeout(() => { confirmDelete.value = false }, 3500)
    return
  }
  window.clearTimeout(confirmTimer)
  try {
    for (const id of selectedIds.value) {
      await bins.removeComponent(id)
    }
  } finally {
    await bins.refreshAll().catch(() => undefined)
    exitBatch()
  }
}

const bins = useBinsStore()

// ---------- 拖动搬家：把格子拖到虚线空格 ----------
const dragComp = ref<ComponentItem | null>(null)  // 正在拖的元件
const dropKey = ref<string | null>(null)          // 当前悬停的空位
const moveNote = ref<string | null>(null)         // 搬家结果提示
let noteTimer: ReturnType<typeof setTimeout> | undefined

function flashNote(text: string) {
  moveNote.value = text
  window.clearTimeout(noteTimer)
  noteTimer = window.setTimeout(() => { moveNote.value = null }, 4500)
}

// 与操作流水、引导条一致的口径：区/层/格（格从 0 起）
function posText(pos: BinPosition): string {
  return `${pos.zone}区/${pos.layer}层/${pos.slot}格`
}

function onDragStart(ev: DragEvent, comp: ComponentItem) {
  if (batchMode.value) {  // 多选模式下点击是选中，别误拖
    ev.preventDefault()
    return
  }
  dragComp.value = comp
  moveNote.value = null
  if (ev.dataTransfer) {
    ev.dataTransfer.effectAllowed = 'move'
    ev.dataTransfer.setData('text/plain', String(comp.id))
  }
}

function onDragEnd() {
  dragComp.value = null
  dropKey.value = null
}

function onDragOver(pos: BinPosition, ev: DragEvent) {
  if (!dragComp.value) return
  ev.preventDefault()  // 只有 preventDefault 才允许放下
  if (ev.dataTransfer) ev.dataTransfer.dropEffect = 'move'
  dropKey.value = positionKey(pos)
}

function onDragLeave(pos: BinPosition) {
  if (dropKey.value === positionKey(pos)) dropKey.value = null
}

async function onDrop(pos: BinPosition) {
  const comp = dragComp.value
  dragComp.value = null
  dropKey.value = null
  if (!comp) return
  const from = { zone: comp.zone, layer: comp.layer, slot: comp.slot }
  if (positionKey(from) === positionKey(pos)) return
  try {
    await bins.moveComponent(comp.id, pos)
    flashNote(`已把「${comp.name}」从 ${posText(from)} 搬到 ${posText(pos)}`)
  } catch (e) {
    flashNote(`搬家失败：${e instanceof Error ? e.message : String(e)}`)
  }
}

function zoneCells(zone: number): number {
  const [rows, cols] = zoneGrid(bins.layout, zone)
  return rows * cols
}

function zoneCols(zone: number): number {
  return zoneGrid(bins.layout, zone)[1]
}

function compAt(pos: BinPosition): ComponentItem | undefined {
  return bins.compsByKey[positionKey(pos)]
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
  <div class="fade-up mx-auto flex w-[min(1400px,calc(100%-24px))] flex-col gap-4 pb-16">
    <!-- 批量操作条 -->
    <div class="flex items-center justify-end gap-2">
      <template v-if="batchMode">
        <span class="chip num">已选 {{ selectedIds.size }} 个</span>
        <button class="btn !py-1.5 text-xs" @click="selectAll">全选</button>
        <button class="btn !py-1.5 text-xs" :disabled="selectedIds.size === 0" @click="clearSelection">清空选择</button>
        <button class="btn btn-danger !py-1.5 text-xs" :disabled="selectedIds.size === 0" @click="deleteSelected">
          <Trash2 :size="13" /> {{ confirmDelete ? '确认删除？' : '删除所选' }}
        </button>
        <button class="btn !py-1.5 text-xs" :disabled="selectedIds.size === 0"
                title="清空所选元件的供应商料号（工程专用编号）" @click="clearSupplierParts">
          {{ confirmClearSupplier ? '确认清空？' : '清除供应商料号' }}
        </button>
        <button class="btn btn-ghost !py-1.5 text-xs" @click="exitBatch">退出多选</button>
      </template>
      <template v-else>
        <span class="text-[11.5px]" style="color: var(--text-faint)">按住格子拖到虚线空格即可搬家</span>
        <button class="btn !py-1.5 text-xs" title="批量选择后可删除" @click="enterBatch">
          ☑ 多选
        </button>
      </template>
    </div>

    <!-- 搬家进行中：提示可放下的位置 -->
    <div
      v-if="dragComp"
      class="glass-panel flex items-center gap-3 rounded-2xl px-4 py-2.5"
      style="border-color: color-mix(in srgb, var(--accent) 55%, var(--line))"
    >
      <Move :size="16" style="color: var(--accent)" />
      <span class="text-[13px] font-semibold">
        正在搬「{{ dragComp.name }}」（{{ posText({ zone: dragComp.zone, layer: dragComp.layer, slot: dragComp.slot }) }}）
      </span>
      <span class="text-[12px]" style="color: var(--text-dim)">松手放到虚线空位即可，按 Esc 放弃</span>
    </div>

    <!-- 搬家结果提示 -->
    <div
      v-else-if="moveNote"
      class="glass-panel flex items-center gap-3 rounded-2xl px-4 py-2.5"
      style="border-color: color-mix(in srgb, var(--accent) 45%, var(--line))"
    >
      <Check :size="16" style="color: var(--success)" />
      <span class="text-[13px]">{{ moveNote }}</span>
      <button class="icon-btn ml-auto !h-7 !w-7" title="关闭" @click="moveNote = null"><X :size="13" /></button>
    </div>

    <!-- 游离元件提示：布局缩容后超出网格 -->
    <div
      v-if="bins.orphanComps.length > 0"
      class="glass-panel flex flex-wrap items-center gap-3 rounded-2xl px-4 py-3"
      style="border-color: color-mix(in srgb, var(--warn) 55%, var(--line))"
    >
      <TriangleAlert :size="18" style="color: var(--warn)" />
      <span class="text-[13px] font-semibold">
        {{ bins.orphanComps.length }} 个元件超出当前网格（游离区）
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
      class="glass-panel rounded-3xl p-4 sm:p-6"
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
          <span class="chip !text-[10.5px]">共 {{ bins.layout.layer_count }} 层</span>
          <span class="chip !text-[10.5px] num">
            每层 {{ zoneGrid(bins.layout, zone)[0] }}×{{ zoneGrid(bins.layout, zone)[1] }} 格
          </span>
        </div>
      </div>

      <div class="flex flex-col gap-6">
        <div v-for="layer in bins.layout.layer_count" :key="layer">
          <div class="mb-2 flex items-center gap-2">
            <span class="mono text-[11px] font-bold tracking-[0.1em]" style="color: var(--text-faint)">
              层 {{ layer }}
            </span>
            <div class="h-px flex-1" style="background: var(--line)" />
          </div>

          <div class="overflow-x-auto px-1 pt-2.5 pb-2">
          <div
            class="grid gap-2.5"
            :style="{ gridTemplateColumns: 'repeat(' + zoneCols(zone) + ', minmax(118px, 1fr))' }"
          >
            <template
              v-for="slot in zoneCells(zone)"
              :key="slot"
            >
              <!-- 有料格子 -->
              <BinCard
                v-if="compAt({ zone, layer, slot: slot - 1 })"
                :comp="compAt({ zone, layer, slot: slot - 1 })!"
                :flashing="!!bins.flashKeys[positionKey({ zone, layer, slot: slot - 1 })]"
                :guide="bins.guideKey === positionKey({ zone, layer, slot: slot - 1 })"
                :selectable="batchMode"
                :selected="batchMode && selectedIds.has(compAt({ zone, layer, slot: slot - 1 })!.id)"
                :show-supplier="batchMode"
                :draggable="!batchMode"
                @click="onCard($event)"
                @dragstart="onDragStart($event, compAt({ zone, layer, slot: slot - 1 })!)"
                @dragend="onDragEnd"
              />
              <!-- 空位：虚线占位卡，点击新建 -->
              <button
                v-else
                class="card-empty grid min-h-[96px] place-items-center rounded-[14px]"
                :class="{
                  'drop-ready': !!dragComp,
                  'drop-target': !!dragComp && dropKey === positionKey({ zone, layer, slot: slot - 1 }),
                }"
                :title="dragComp ? '放这里：把元件搬到这个空位' : '空位：点击新建元件'"
                @click="emit('create', { zone, layer, slot: slot - 1 })"
                @dragover="onDragOver({ zone, layer, slot: slot - 1 }, $event)"
                @dragleave="onDragLeave({ zone, layer, slot: slot - 1 })"
                @drop.prevent="onDrop({ zone, layer, slot: slot - 1 })"
              >
                <Plus :size="20" />
              </button>
            </template>
          </div>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>