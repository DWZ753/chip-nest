<script setup lang="ts">
import { computed } from 'vue'

import type { ComponentItem } from '../api/types'

const props = defineProps<{
  comp: ComponentItem
  flashing: boolean
  guide: boolean
}>()

const emit = defineEmits<{ click: [ComponentItem] }>()

const bandCls = computed(() => {
  const q = props.comp.quantity
  const t = props.comp.threshold
  if (q <= 0 || (t > 0 && q < t / 2)) return 'band-low'
  if (t > 0 && q < t) return 'band-warn'
  return 'band-ok'
})

// 色带宽度：以 threshold 为满刻度；threshold=0 时按有/无货
const bandWidth = computed(() => {
  const { quantity: q, threshold: t } = props.comp
  if (q <= 0) return '0%'
  if (t <= 0) return '100%'
  return Math.min(100, Math.round((q / t) * 100)) + '%'
})

const title = computed(() =>
  [props.comp.name, props.comp.value, props.comp.package].filter(Boolean).join(' · '),
)
</script>

<template>
  <div
    class="bin-card group"
    :class="{ 'search-hit': flashing, 'guide-now': guide }"
    :title="title"
    role="button"
    tabindex="0"
    @click="emit('click', comp)"
    @keydown.enter="emit('click', comp)"
  >
    <!-- 头行：长名称 flex 截断，灯号/数量作为独立元素，hover 才显示数量 -->
    <div class="flex items-center gap-1.5">
      <span
        class="card-title min-w-0 flex-1 truncate text-[13.5px] font-bold leading-snug"
        :title="comp.name"
      >{{ comp.name }}</span>
      <span
        v-if="comp.led_index !== null"
        class="chip chip-led flex-shrink-0 !px-1.5 !text-[9.5px]"
        title="灯带序号"
      >LED{{ comp.led_index }}</span>
      <span
        class="qty-hover chip qty-chip num flex-shrink-0 !px-1.5 !text-[10px]"
        title="当前库存"
      >× {{ comp.quantity }}</span>
    </div>

    <div class="meta-row mt-1 flex flex-wrap items-center gap-1">
      <span
        v-if="comp.value"
        class="chip chip-value mono !px-2"
        style="background: color-mix(in srgb, var(--accent) 14%, var(--panel))"
      >{{ comp.value }}</span>
      <span
        v-if="comp.package"
        class="chip chip-pkg mono"
      >{{ comp.package }}</span>
    </div>

    <!-- 用户自定义标签：最多显示 2 个，其余折叠为 +N -->
    <div v-if="comp.tags?.length" class="meta-tags mt-0.5 flex items-center gap-1 overflow-hidden">
      <span v-for="tag in comp.tags.slice(0, 2)" :key="tag"
            class="chip chip-tag mono !px-1.5 !text-[9px]" :title="tag">#{{ tag }}</span>
      <span v-if="comp.tags.length > 2" class="chip mono !px-1.5 !text-[9px]"
            title="更多标签">+{{ comp.tags.length - 2 }}</span>
    </div>

    <!-- 厂商料号（MPN）：采购/识别关键字段，窄格自动隐藏 -->
    <div
      v-if="comp.manufacturer_part"
      class="mpn-line mono mt-0.5 truncate text-[9.5px]"
      style="color: var(--text-faint)"
      :title="comp.manufacturer_part"
    >{{ comp.manufacturer_part }}</div>

    <div class="flex-1" />
    <div class="band -mx-3 mt-2" :class="bandCls" :style="{ width: bandWidth }" />
  </div>
</template>