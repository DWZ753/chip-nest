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

const bandCls = computed(() => {
  const q = props.comp.quantity
  const t = props.comp.threshold
  if (q <= 0) return 'band-empty'
  if (t > 0 && q < t / 2) return 'band-low'
  if (t > 0 && q < t) return 'band-warn'
  return 'band-ok'
})

// 色带宽度：以 threshold 为满刻度；0 库存满格告急，避免“条消失=不紧急”的错觉
const bandWidth = computed(() => {
  const { quantity: q, threshold: t } = props.comp
  if (q <= 0) return '100%'
  if (t <= 0) return '100%'
  return Math.min(100, Math.round((q / t) * 100)) + '%'
})

const fields = computed<string[]>(() => props.comp.display_fields ?? ['value', 'package'])
// 显示标签：未单独挑选时，自动用前两个普通标签兜底，保证标签一定会出现在格子上
const cardTags = computed<string[]>(() => {
  const shown = props.comp.display_tags ?? []
  if (shown.length) return shown
  return props.comp.tags ?? []
})
const show = (name: string) => fields.value.includes(name)

// ---------- 标签自适应：按行内实际可用宽度决定显示几个，其余折叠为 +N ----------
const tagsRow = ref<HTMLElement | null>(null)
const measureEl = ref<HTMLElement | null>(null)
const visibleTags = ref<string[]>([])
const hiddenCount = ref(0)
let observer: ResizeObserver | null = null

function recomputeTags() {
  const all = cardTags.value
  const row = tagsRow.value
  const box = measureEl.value
  if (!row || !box) return
  const width = row.clientWidth
  const nodes = Array.from(box.children) as HTMLElement[]
  if (!all.length || !width || nodes.length < all.length + 1) {
    visibleTags.value = all
    hiddenCount.value = 0
    return
  }
  const chipW = nodes.slice(0, all.length).map((n) => n.getBoundingClientRect().width + 4)
  const plusW = nodes[all.length].getBoundingClientRect().width + 4
  const chosen: string[] = []
  let used = 0
  for (let i = 0; i < all.length; i += 1) {
    const rest = all.length - i - 1
    const need = chipW[i] + (rest > 0 ? plusW : 0)
    if (used + need <= width || chosen.length === 0) {
      chosen.push(all[i])
      used += chipW[i]
    } else {
      break
    }
  }
  visibleTags.value = chosen
  hiddenCount.value = all.length - chosen.length
}

onMounted(async () => {
  await nextTick()
  recomputeTags()
  if (typeof ResizeObserver !== 'undefined' && tagsRow.value) {
    observer = new ResizeObserver(() => recomputeTags())
    observer.observe(tagsRow.value)
  }
})

onBeforeUnmount(() => observer?.disconnect())

watch(cardTags, async () => {
  await nextTick()
  recomputeTags()
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
    <!-- 名称最多两行；灯号/数量常驻右侧（预留位置，悬停不再跳动） -->
    <div class="flex items-start gap-1.5">
      <span
        class="card-title card-name min-w-0 flex-1 text-[13px] font-bold leading-snug"
        :title="comp.name"
      >{{ comp.name }}</span>
      <span class="meta-side flex flex-shrink-0 items-center gap-1">
        <span
          v-if="comp.led_index !== null && !selectable"
          class="chip chip-led !px-1.5 !text-[9.5px]"
          title="灯带序号"
        >LED{{ comp.led_index }}</span>
        <span
          v-if="!selectable"
          class="chip qty-chip num !px-1.5 !text-[10px]"
          title="当前库存"
        >× {{ comp.quantity }}</span>
      </span>
    </div>

    <div class="meta-row mt-1 flex flex-wrap items-center gap-1">
      <span
        v-if="show('value') && comp.value"
        class="chip chip-value mono !px-2"
        style="background: color-mix(in srgb, var(--accent) 14%, var(--panel))"
      >{{ comp.value }}</span>
      <span
        v-if="show('package') && comp.package"
        class="chip chip-pkg mono"
      >{{ comp.package }}</span>
      <span
        v-if="show('mpn') && comp.manufacturer_part"
        class="chip chip-mpn mono !px-1.5 !text-[9.5px]"
        :title="'厂商料号 ' + comp.manufacturer_part"
      >{{ comp.manufacturer_part }}</span>
      <span
        v-if="show('supplier') && comp.supplier_part"
        class="chip chip-supplier mono !px-1.5 !text-[9.5px]"
        :title="'供应商料号 ' + comp.supplier_part"
      >{{ comp.supplier_part }}</span>
    </div>

    <!-- 显示标签：单行自适应，放不下的折叠为 +N（不换行、不压到状态条） -->
    <div v-if="cardTags.length" ref="tagsRow"
         class="mt-1 flex items-center gap-1 overflow-hidden whitespace-nowrap">
      <span v-for="tag in visibleTags" :key="tag"
            class="chip chip-tag-show mono !px-1.5 !text-[9.5px] font-bold"
            :title="tag">#{{ tag }}</span>
      <span v-if="hiddenCount > 0"
            class="chip chip-tag-show mono !px-1 !text-[8.5px] font-bold"
            :title="cardTags.join('、')">+{{ hiddenCount }}</span>
    </div>

    <!-- 隐藏测量层：用真实渲染宽度决定能放几个标签 -->
    <div ref="measureEl" class="tag-measure" aria-hidden="true">
      <span v-for="tag in cardTags" :key="'m-' + tag"
            class="chip chip-tag-show mono !px-1.5 !text-[9.5px] font-bold">#{{ tag }}</span>
      <span class="chip chip-tag-show mono !px-1 !text-[8.5px] font-bold">+99</span>
    </div>

    <div class="flex-1" />
    <div class="band-track -mx-3 mt-2">
      <div class="band" :class="bandCls" :style="{ width: bandWidth }" />
    </div>
    <!-- 多选时临时把供应商料号显示在格子中间（便于清理工程专用编号） -->
    <div v-if="showSupplier && comp.supplier_part" class="supplier-overlay"
         :title="'供应商料号 ' + comp.supplier_part">
      {{ comp.supplier_part }}
    </div>

    <!-- 搜索命中的辉光层（线性淡出） -->
    <div v-if="flashing" class="flash-layer" />
  </div>
</template>