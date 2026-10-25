<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import type { CSSProperties } from 'vue'

import { create_motion } from '../../utils/motion'
import { MotionStrip } from '../../utils/motion_state'

const props = defineProps<{ value: string; change_key: number }>()
const root = ref<HTMLElement | null>(null)
const animating = ref(false)
const placeholder = ref('')
const position = ref(0)
const text_style = ref<CSSProperties>({})
const texts = ref([{ key: String(props.change_key), value: props.value }])
const strip = new MotionStrip(String(props.change_key))
const motion = create_motion({ position: 0 }, values => {
  position.value = values.position
}, () => { animating.value = false })
let target = 0

/** @brief Give typing and focus precedence over visual handoff. */
function finish() {
  motion.set({ position: target }, true)
  animating.value = false
}

/** @brief Keep read-only text pages adjacent inside the persistent input. */
function page_style(key: string): CSSProperties {
  const offset = strip.offset(key)

  return {
    ...text_style.value,
    display: offset === undefined ? 'none' : undefined,
    transform: `translate3d(0,${((offset ?? 0) - position.value) * 100}%,0)`,
  }
}

watch(() => [props.value, props.change_key] as const,
  ([value, identity], [previous_value, previous_identity]) => {
    const key = String(identity)
    const page = texts.value.find(item => item.key === key)
    const input = root.value?.querySelector('input')

    if (page) page.value = value
    else texts.value.push({ key, value })

    const order = texts.value.map(item => item.key)
      .sort((a, b) => Number(a) - Number(b))

    if (identity !== previous_identity) {
      target = strip.select(key, motion.read().position, order)
    }
    if (identity === previous_identity || value === previous_value || !input ||
      document.activeElement === input) {
      finish()
      return
    }

    placeholder.value = input.placeholder
    const style = getComputedStyle(input)
    text_style.value = {
      font: style.font,
      letterSpacing: style.letterSpacing,
      padding: style.padding,
    }
    animating.value = true
    motion.set({ position: target })
  })

onBeforeUnmount(motion.stop)
</script>

<template>
  <div ref="root" class="motion-field"
       :class="{ 'motion-field-masked': animating }"
       @focusin="finish" @pointerdown="finish">
    <slot />
    <div v-if="animating" class="motion-field-viewport"
         aria-hidden="true" inert>
      <span v-for="page in texts" :key="page.key"
            class="motion-field-page" :style="page_style(page.key)"
            :class="{ 'motion-field-placeholder': !page.value }">
        {{ page.value || placeholder }}
      </span>
    </div>
  </div>
</template>
