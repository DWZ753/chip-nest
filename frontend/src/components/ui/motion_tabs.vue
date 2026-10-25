<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { create_motion } from '../../utils/motion'

const props = defineProps<{
  modelValue: string
  tabs: { key: string; label: string }[]
  label: string
  disabled?: boolean
}>()
const emit = defineEmits<{ 'update:modelValue': [string] }>()
const root = ref<HTMLElement | null>(null)
const indicator = ref({ width: '0px', transform: 'translateX(0px)' })
const motion = create_motion({ x: 0, width: 0 }, values => {
  indicator.value = {
    width: `${values.width}px`,
    transform: `translateX(${values.x}px)`,
  }
})
let observer: ResizeObserver | undefined
let measured = false

/** 根据按钮实际尺寸定位滑块，兼容字号缩放与窗口尺寸变化。 */
function measure_indicator() {
  const button = root.value?.querySelector<HTMLElement>(
    '[aria-pressed="true"]',
  )
  if (!button) return
  motion.set({ width: button.offsetWidth, x: button.offsetLeft }, !measured)
  measured = true
}

watch(() => props.modelValue, async () => {
  await nextTick()
  measure_indicator()
})

onMounted(() => {
  measure_indicator()
  observer = new ResizeObserver(measure_indicator)
  if (root.value) {
    observer.observe(root.value)
    root.value.querySelectorAll('button').forEach(button =>
      observer?.observe(button))
  }
})

onBeforeUnmount(() => {
  observer?.disconnect()
  motion.stop()
})
</script>

<template>
  <nav ref="root" class="motion-tabs mb-4" :aria-label="label">
    <span class="motion-tabs-indicator" :style="indicator"
          aria-hidden="true" />
    <button v-for="tab in tabs" :key="tab.key" type="button"
            class="motion-tab" :aria-pressed="modelValue === tab.key"
            :disabled="disabled"
            @click="emit('update:modelValue', tab.key)">
      {{ tab.label }}
    </button>
  </nav>
</template>
