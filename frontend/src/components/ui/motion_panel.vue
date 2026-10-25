<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { ComponentPublicInstance, CSSProperties } from 'vue'

import { create_motion } from '../../utils/motion'
import { MotionStrip } from '../../utils/motion_state'

const props = defineProps<{
  active_key: string
  page_order: string[]
}>()
const frame = ref<HTMLElement | null>(null)
const visited = ref([props.active_key])
const position = ref(0)
const height = ref<number | null>(null)
const limit = ref<number | null>(null)
const moving = ref(false)
const revision = ref(0)
const pages = new Map<string, HTMLElement>()
const strip = new MotionStrip(props.active_key)
const motion = create_motion({ position: 0, height: 0 }, values => {
  position.value = values.position
  height.value = values.height
}, () => { moving.value = false })
let observer: ResizeObserver | undefined
let busy_observer: MutationObserver | undefined

/** @brief Register persistent pages for resize and loading measurements. */
function register_page(
  key: string, element: Element | ComponentPublicInstance | null,
) {
  const previous = pages.get(key)

  if (previous === element) return
  if (previous) observer?.unobserve(previous)
  if (element instanceof HTMLElement) {
    pages.set(key, element)
    observer?.observe(element)
  } else {
    pages.delete(key)
  }
}

/** @brief Include margins when subtracting the persistent dialog chrome. */
function outer_height(element: Element): number {
  const style = getComputedStyle(element)

  return (element as HTMLElement).offsetHeight +
    Number.parseFloat(style.marginTop) + Number.parseFloat(style.marginBottom)
}

/** @brief Fit the selected page to the viewport without reflowing old pages. */
async function measure_height() {
  const element = frame.value
  const parent = element?.parentElement
  const key = props.active_key

  if (!element || !parent) return

  const style = getComputedStyle(parent)
  const zoom = Number.parseFloat(getComputedStyle(document.body).zoom) || 1
  const maximum = Number.parseFloat(style.maxHeight)
  const available = Math.min(Number.isFinite(maximum) ? maximum : Infinity,
    window.innerHeight / zoom - 32)
  const fixed = Array.from(parent.children)
    .filter(child => child !== element)
    .reduce((sum, child) => sum + outer_height(child), 0) +
    Number.parseFloat(style.paddingTop) +
    Number.parseFloat(style.paddingBottom) +
    Number.parseFloat(style.borderTopWidth) +
    Number.parseFloat(style.borderBottomWidth)

  limit.value = Math.max(0, Math.floor(available - fixed))
  await nextTick()

  const page = pages.get(key)

  if (key !== props.active_key || !page ||
    page.querySelector('[aria-busy="true"]')) return

  motion.set({ height: Number.parseFloat(getComputedStyle(page).height) },
    height.value === null)
}

/** @brief Position pages on a shared strip, including rapid third targets. */
function page_style(key: string): CSSProperties {
  void revision.value

  const offset = strip.offset(key)

  return {
    position: height.value === null && key === props.active_key
      ? 'relative' : undefined,
    display: offset === undefined ? 'none' : undefined,
    visibility: offset === undefined ||
      Math.abs(offset - position.value) > 1.001 ? 'hidden' : undefined,
    transform: `translate3d(${((offset ?? 0) - position.value) * 100}%,0,0)`,
    maxHeight: limit.value === null ? undefined : `${limit.value}px`,
  }
}

watch(() => props.active_key, async key => {
  const target = strip.select(key, motion.read().position, props.page_order)

  if (!visited.value.includes(key)) visited.value.push(key)
  revision.value += 1
  moving.value = true
  await nextTick()

  if (key !== props.active_key) return

  motion.set({ position: target })
  void measure_height()
})

onMounted(() => {
  observer = new ResizeObserver(() => void measure_height())
  pages.forEach(page => observer?.observe(page))
  busy_observer = new MutationObserver(() => void measure_height())
  if (frame.value) {
    busy_observer.observe(frame.value, {
      attributes: true, attributeFilter: ['aria-busy'], subtree: true,
    })
  }
  void measure_height()
  window.addEventListener('resize', measure_height)
})

onBeforeUnmount(() => {
  motion.stop()
  observer?.disconnect()
  busy_observer?.disconnect()
  window.removeEventListener('resize', measure_height)
})
</script>

<template>
  <div ref="frame" class="motion-panel"
       :data-motion-key="active_key" :data-motion-moving="moving"
       :style="{ height: height === null ? undefined : `${height}px` }">
    <div v-for="page_key in visited" :key="page_key"
         :ref="element => register_page(page_key, element)"
         class="motion-panel-page" :data-motion-page="page_key"
         :style="page_style(page_key)"
         :inert="page_key !== active_key"
         :aria-hidden="page_key !== active_key">
      <slot :page_key="page_key" />
    </div>
  </div>
</template>
