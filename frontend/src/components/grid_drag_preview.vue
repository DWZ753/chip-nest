<script setup lang="ts">
import { computed } from 'vue'
import type { CSSProperties } from 'vue'

import type { GridDragController } from '../composables/use_grid_drag'
import BinCard from './BinCard.vue'

const props = defineProps<{ controller: GridDragController }>()
const drag = computed(() => props.controller.state.value)

/** @brief Render pointer motion without rebuilding the shelf. */
const primary_style = computed<CSSProperties>(() => {
  const pose = props.controller.pose.value

  return {
    width: `${pose.width}px`, height: `${pose.height}px`,
    transform: `translate3d(${pose.x}px,${pose.y}px,0) scale(${pose.scale})`,
    transformOrigin: `${drag.value?.grab_x}px ${drag.value?.grab_y}px`,
  }
})
const other_style = computed<CSSProperties>(() => {
  const pose = props.controller.pose.value

  return {
    width: `${pose.other_width}px`, height: `${pose.other_height}px`,
    transform: `translate3d(${pose.other_x}px,${pose.other_y}px,0)`,
  }
})
</script>

<template>
  <Teleport to="body">
    <div v-if="drag" class="grid-drag-ghost" :style="primary_style"
         aria-hidden="true" inert>
      <BinCard :comp="drag.component" :flashing="false" :guide="false"
               :shared="drag.shared" />
    </div>
    <div v-if="drag?.other" class="grid-drag-ghost" :style="other_style"
         aria-hidden="true" inert>
      <BinCard :comp="drag.other" :flashing="false" :guide="false" />
    </div>
  </Teleport>
</template>
