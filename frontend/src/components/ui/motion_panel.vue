<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'

const frame = ref<HTMLElement | null>(null)
const content = ref<HTMLElement | null>(null)
const height = ref<number | null>(null)
const limit = ref<number | null>(null)
let observer: ResizeObserver | undefined
let busy_observer: MutationObserver | undefined

/** 固定区域包含自身高度与外边距，不参与内容区伸缩。 */
function outer_height(element: Element): number {
  const style = getComputedStyle(element)
  return (element as HTMLElement).offsetHeight
    + Number.parseFloat(style.marginTop)
    + Number.parseFloat(style.marginBottom)
}

/** 测量自然内容高度；限制在视口内，由高度过渡带动居中位置。 */
async function measure_height() {
  const element = frame.value
  const parent = element?.parentElement
  if (!element || !parent || !content.value) return
  const style = getComputedStyle(parent)
  const zoom = Number.parseFloat(getComputedStyle(document.body).zoom) || 1
  const available = Math.min(
    Number.parseFloat(style.maxHeight),
    window.innerHeight / zoom - 32,
  )
  const fixed = Array.from(parent.children)
    .filter((child) => child !== element)
    .reduce((sum, child) => sum + outer_height(child), 0)
    + Number.parseFloat(style.paddingTop)
    + Number.parseFloat(style.paddingBottom)
    + Number.parseFloat(style.borderTopWidth)
    + Number.parseFloat(style.borderBottomWidth)
  limit.value = Math.max(0, Math.floor(available - fixed))
  await nextTick()
  const inner = content.value
  if (inner && !inner.querySelector('[aria-busy="true"]')) {
    height.value = Math.ceil(Number.parseFloat(getComputedStyle(inner).height))
  }
}

onMounted(() => {
  void measure_height()
  observer = new ResizeObserver(() => void measure_height())
  if (content.value) observer.observe(content.value)
  busy_observer = new MutationObserver(() => void measure_height())
  if (content.value) {
    busy_observer.observe(content.value, {
      attributes: true, attributeFilter: ['aria-busy'], subtree: true,
    })
  }
  window.addEventListener('resize', measure_height)
})

onBeforeUnmount(() => {
  observer?.disconnect()
  busy_observer?.disconnect()
  window.removeEventListener('resize', measure_height)
})
</script>

<template>
  <div ref="frame" class="motion-panel"
       :style="{ height: height === null ? undefined : height + 'px' }">
    <div ref="content" class="motion-panel-content"
         :style="{ maxHeight: limit === null ? undefined : limit + 'px' }">
      <slot />
    </div>
  </div>
</template>
