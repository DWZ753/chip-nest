<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import type { ComponentItem } from '../api/types'

const props = defineProps<{
  comp: ComponentItem
  flashing: boolean
  guide: boolean
  selectable?: boolean
  selected?: boolean
  showSupplier?: boolean
}>()

const emit = defineEmits<{ click: [ComponentItem] }>()

const FIELD_ORDER = ['value', 'package', 'mpn', 'supplier']
const FIELD_LABEL: Record<string, string> = {
  value: '标称值',
  package: '封装',
  mpn: '厂商料号',
  supplier: '供应商料号',
}

const fields = computed<string[]>(() => props.comp.display_fields ?? ['value', 'package'])
const shownTagNames = computed<string[]>(() => props.comp.display_tags ?? [])

function fieldText(key: string): string {
  const c = props.comp
  if (key === 'value') return c.value ?? ''
  if (key === 'package') return c.package ?? ''
  if (key === 'mpn') return c.manufacturer_part ?? ''
  if (key === 'supplier') return c.supplier_part ?? ''
  return ''
}

// 统一顺序：card_items 里字段与 "#标签" 混排；缺省时字段在前、标签在后
const orderTokens = computed<string[]>(() => {
  const custom = props.comp.card_items ?? []
  if (custom.length) return custom
  return [...FIELD_ORDER, ...(props.comp.tags ?? []).map((t) => '#' + t)]
})

interface Chip { token: string; kind: 'field' | 'tag'; key: string; text: string }
const chips = computed<Chip[]>(() => {
  const out: Chip[] = []
  for (const token of orderTokens.value) {
    if (token.startsWith('#')) {
      const name = token.slice(1)
      const visible = shownTagNames.value.length ? shownTagNames.value.includes(name) : true
      if (visible) out.push({ token, kind: 'tag', key: name, text: '#' + name })
      continue
    }
    if (!fields.value.includes(token)) continue
    const text = fieldText(token)
    if (!text) continue
    out.push({ token, kind: 'field', key: token, text })
  }
  return out
})

function chipClass(chip: Chip): string {
  if (chip.kind === 'tag') return 'chip-tag-show mono font-bold'
  if (chip.key === 'value') return 'chip-value mono'
  if (chip.key === 'package') return 'chip-pkg mono'
  if (chip.key === 'mpn') return 'chip-mpn mono'
  return 'chip-supplier mono'
}

// ---------- 自适应：按行内实际宽度决定显示几个，其余折叠为 +N ----------
const chipsRow = ref<HTMLElement | null>(null)
const measureEl = ref<HTMLElement | null>(null)
const visibleCount = ref(0)
let observer: ResizeObserver | null = null

function recompute() {
  const list = chips.value
  const row = chipsRow.value
  const box = measureEl.value
  if (!list.length) { visibleCount.value = 0; return }
  const width = row?.clientWidth ?? 0
  const nodes = Array.from(box?.children ?? []) as HTMLElement[]
  if (!width || nodes.length < list.length + 1) { visibleCount.value = list.length; return }
  const widths = nodes.slice(0, list.length).map((n) => n.getBoundingClientRect().width + 4)
  const plusW = nodes[list.length].getBoundingClientRect().width + 4
  let used = 0
  let count = 0
  for (let i = 0; i < list.length; i += 1) {
    const rest = list.length - i - 1
    const need = widths[i] + (rest > 0 ? plusW : 0)
    if (used + need <= width || count === 0) { used += widths[i]; count += 1 } else break
  }
  visibleCount.value = count
}

onMounted(async () => {
  await nextTick()
  recompute()
  if (typeof ResizeObserver !== 'undefined' && chipsRow.value) {
    observer = new ResizeObserver(() => recompute())
    observer.observe(chipsRow.value)
  }
})
onBeforeUnmount(() => observer?.disconnect())
watch(chips, async () => { await nextTick(); recompute() })

const visibleChips = computed(() => chips.value.slice(0, visibleCount.value))
const hiddenCount = computed(() => Math.max(0, chips.value.length - visibleCount.value))
const hiddenText = computed(() => chips.value.slice(visibleCount.value).map((c) => c.text).join('、'))

const bandCls = computed(() => {
  const q = props.comp.quantity
  const t = props.comp.threshold
  if (q <= 0) return 'band-empty'
  if (t > 0 && q < t / 2) return 'band-low'
  if (t > 0 && q < t) return 'band-warn'
  return 'band-ok'
})

const bandWidth = computed(() => {
  const { quantity: q, threshold: t } = props.comp
  if (q <= 0 || t <= 0) return '100%'
  return Math.min(100, Math.round((q / t) * 100)) + '%'
})

const title = computed(() => {
  const base = [props.comp.name, props.comp.value, props.comp.package].filter(Boolean)
  const tags = props.comp.tags ?? []
  return tags.length ? base.join(' · ') + ' · #' + tags.join(' #') : base.join(' · ')
})
</script>

<template>
  <div
    class="bin-card group"
    :class="{ 'search-hit': flashing, 'guide-now': guide,
              'card-selected': selected,
              'has-supplier': showSupplier && !!comp.supplier_part }"
    :title="title"
    role="button"
    tabindex="0"
    @click="emit('click', comp)"
    @keydown.enter="emit('click', comp)"
  >
    <!-- 名称最多两行；灯号/数量常驻占位，悬停才显现 -->
    <div class="flex items-start gap-1.5">
      <span class="card-title card-name min-w-0 flex-1 text-[13px] font-bold leading-snug"
            :title="comp.name">{{ comp.name }}</span>
      <span class="meta-side flex flex-shrink-0 items-center gap-1">
        <span v-if="comp.led_index !== null && !selectable"
              class="chip chip-led !px-1.5 !text-[9.5px]" title="灯带序号">LED{{ comp.led_index }}</span>
        <span v-if="!selectable" class="chip qty-chip num !px-1.5 !text-[10px]"
              title="当前库存">× {{ comp.quantity }}</span>
      </span>
    </div>

    <!-- 统一显示链：字段与标签同一序列，单行自适应，放不下折叠为 +N -->
    <div v-if="chips.length" ref="chipsRow" class="mt-1 flex items-center gap-1 overflow-hidden whitespace-nowrap">
      <span v-for="chip in visibleChips" :key="chip.token"
            class="chip !px-1.5 !text-[9.5px]" :class="chipClass(chip)"
            :title="chip.kind === 'field' ? FIELD_LABEL[chip.key] + ' ' + chip.text : chip.text">
        {{ chip.text }}
      </span>
      <span v-if="hiddenCount > 0" class="chip chip-tag-show mono !px-1 !text-[8.5px] font-bold"
            :title="hiddenText">+{{ hiddenCount }}</span>
    </div>

    <!-- 离屏测量层（真实渲染宽度） -->
    <div ref="measureEl" class="tag-measure" aria-hidden="true">
      <span v-for="chip in chips" :key="'m-' + chip.token"
            class="chip !px-1.5 !text-[9.5px]" :class="chipClass(chip)">{{ chip.text }}</span>
      <span class="chip chip-tag-show mono !px-1 !text-[8.5px] font-bold">+99</span>
    </div>

    <div class="flex-1" />
    <div class="band-track -mx-3 mt-2">
      <div class="band" :class="bandCls" :style="{ width: bandWidth }" />
    </div>

    <!-- 多选时临时显示供应商料号 -->
    <div v-if="showSupplier && comp.supplier_part" class="supplier-overlay"
         :title="'供应商料号 ' + comp.supplier_part">{{ comp.supplier_part }}</div>

    <div v-if="flashing" class="flash-layer" />
  </div>
</template>
