<script setup lang="ts">
import { computed } from 'vue'

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
const show = (name: string) => fields.value.includes(name)

const title = computed(() =>
  [props.comp.name, props.comp.value, props.comp.package].filter(Boolean).join(' · '),
)
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

    <!-- 展示标签：卡片中部空白区独立成行，任何宽度都显示 -->
    <div v-if="(comp.display_tags ?? []).length"
         class="mt-1 flex flex-wrap items-center gap-1">
      <template v-for="tag in (comp.display_tags ?? []).slice(0, 2)" :key="tag">
        <span class="chip chip-tag-show mono !px-1.5 !text-[9.5px] font-bold"
              :title="tag">#{{ tag }}</span>
      </template>
      <span v-if="(comp.display_tags ?? []).length > 2"
            class="chip chip-tag-show mono !px-1 !text-[8.5px] font-bold"
            :title="(comp.display_tags ?? []).join('、')">+{{ comp.display_tags.length - 2 }}</span>
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