<script setup lang="ts">
import { computed, ref } from 'vue'
import { Plus, Trash2, TriangleAlert } from '@lucide/vue'

import type { ComponentItem } from '../api/types'
import { positionKey, useBinsStore, zoneName, type BinPosition } from '../stores/bins'
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

function toggleSelect(comp: ComponentItem) {
  const next = new Set(selectedIds.value)
  if (next.has(comp.id)) next.delete(comp.id)
  else next.add(comp.id)
  selectedIds.value = next
}

function onCard(comp: ComponentItem) {
  if (batchMode.value) toggleSelect(comp)
  else emit('edit', comp)
}

async function deleteSelected() {
  if (!confirmDelete.value) {
    confirmDelete.value = true
    window.clearTimeout(confirmTimer)
    confirmTimer = window.setTimeout(() => { confirmDelete.value = false }, 3500)
    return
  }
  window.clearTimeout(confirmTimer)
  for (const id of selectedIds.value) {
    await bins.removeComponent(id)
  }
  exitBatch()
}

const bins = useBinsStore()

const cellsPerLayer = computed(
  () => bins.layout.row_count * bins.layout.col_count,
)

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
        <button class="btn btn-danger !py-1.5 text-xs" @click="deleteSelected">
          <Trash2 :size="13" /> {{ confirmDelete ? '确认删除？' : '删除所选' }}
        </button>
        <button class="btn btn-ghost !py-1.5 text-xs" @click="exitBatch">退出多选</button>
      </template>
      <button v-else class="btn !py-1.5 text-xs" title="批量选择后可删除" @click="enterBatch">
        ☑ 多选
      </button>
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
          <h2 class="text-xl font-extrabold tracking-[0.12em]">
            {{ zoneName(bins.layout, zone) }}
          </h2>
        </div>
        <div class="mb-0.5 flex items-center gap-1.5">
          <span class="chip mono !text-[10px]">共 {{ bins.layout.layer_count }} 层</span>
          <span class="chip mono !text-[10px]">每层 {{ bins.layout.row_count }}×{{ bins.layout.col_count }} 格</span>
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
            :style="{ gridTemplateColumns: 'repeat(' + bins.layout.col_count + ', minmax(118px, 1fr))' }"
          >
            <template
              v-for="slot in cellsPerLayer"
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
                @click="onCard($event)"
              />
              <!-- 空位：虚线占位卡，点击新建 -->
              <button
                v-else
                class="card-empty grid min-h-[96px] place-items-center rounded-[14px]"
                title="空位：点击新建元件"
                @click="emit('create', { zone, layer, slot: slot - 1 })"
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