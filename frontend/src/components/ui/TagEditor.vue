<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { Eye, EyeOff, Plus, X } from '@lucide/vue'

// 多标签输入 + 跟手悬浮拖拽排序（Pointer Events 实现，不依赖 HTML5 drag 的默认幽灵图）
const props = withDefaults(defineProps<{
  modelValue: string[]
  shown?: string[]
  suggestions?: string[]
  placeholder?: string
  compact?: boolean
}>(), { shown: () => [], suggestions: () => [], placeholder: '输入后回车添加', compact: false })

const emit = defineEmits<{
  (e: 'update:modelValue', value: string[]): void
  (e: 'update:shown', value: string[]): void
}>()
const draft = ref('')
const inputEl = ref<HTMLInputElement | null>(null)
const listEl = ref<HTMLElement | null>(null)
const focusOpen = ref(false)

const chips = computed({
  get: () => props.modelValue,
  set: (v: string[]) => emit('update:modelValue', v),
})

// ---------- 拖拽状态 ----------
interface DragState {
  from: number
  label: string
  dx: number
  dy: number
  w: number
  x: number
  y: number
  startX: number
  startY: number
}
const drag = ref<DragState | null>(null)
const dropIndex = ref(-1)
const moved = ref(false)

function chipRects(): DOMRect[] {
  const nodes = listEl.value?.querySelectorAll<HTMLElement>('[data-tag-chip]') ?? []
  return Array.from(nodes).map((n) => n.getBoundingClientRect())
}

function startDrag(index: number, ev: PointerEvent) {
  if (ev.button !== 0) return
  const el = ev.currentTarget as HTMLElement
  const r = el.getBoundingClientRect()
  drag.value = {
    from: index,
    label: chips.value[index],
    dx: ev.clientX - r.left,
    dy: ev.clientY - r.top,
    w: r.width,
    x: ev.clientX,
    y: ev.clientY,
    startX: ev.clientX,
    startY: ev.clientY,
  }
  dropIndex.value = index
  moved.value = false
  ev.preventDefault()
  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', endDrag)
  window.addEventListener('pointercancel', endDrag)
}

function onMove(ev: PointerEvent) {
  const d = drag.value
  if (!d) return
  d.x = ev.clientX
  d.y = ev.clientY
  if (!moved.value
      && Math.hypot(ev.clientX - d.startX, ev.clientY - d.startY) > 4) {
    moved.value = true          // 超过 4px 才算拖动，避免点击被误判
  }
  const rects = chipRects()
  let best = d.from
  let bestDist = Number.POSITIVE_INFINITY
  rects.forEach((r, i) => {
    const dist = Math.abs(ev.clientX - (r.left + r.width / 2))
    if (dist < bestDist) { bestDist = dist; best = i }
  })
  dropIndex.value = best
}

function endDrag() {
  window.removeEventListener('pointermove', onMove)
  window.removeEventListener('pointerup', endDrag)
  window.removeEventListener('pointercancel', endDrag)
  const d = drag.value
  const to = dropIndex.value
  const wasMoved = moved.value
  drag.value = null
  dropIndex.value = -1
  moved.value = false
  if (!d || !wasMoved) return
  if (to < 0 || to === d.from) return
  const list = [...chips.value]
  const [item] = list.splice(d.from, 1)
  list.splice(to, 0, item)
  chips.value = list
}

// ---------- 增删 ----------
function addToken(raw: string, useSuggestion = false) {
  const item = raw.trim().slice(0, 20)
  if (!item) return
  const next = useSuggestion ? [item, ...chips.value] : [...chips.value, item]
  chips.value = Array.from(new Set(next)).slice(0, 12)
  draft.value = ''
  focusOpen.value = false
}

function onKeydown(ev: KeyboardEvent) {
  if (ev.key === 'Enter' || ev.key === ',' || ev.key === '，' || ev.key === '、') {
    ev.preventDefault()
    addToken(draft.value)
    return
  }
  if (ev.key === 'Backspace' && !draft.value && chips.value.length) {
    chips.value = chips.value.slice(0, -1)
  }
}

const shown = computed(() => {
  const q = draft.value.trim().toLowerCase()
  const mine = new Set(chips.value)
  return props.suggestions.filter((s) => !mine.has(s)
    && (!q || s.toLowerCase().includes(q))).slice(0, 8)
})

function focusInput() {
  nextTick(() => inputEl.value?.focus())
}

function handleBlur() {
  window.setTimeout(() => {
    focusOpen.value = false
    if (draft.value.trim()) addToken(draft.value)
  }, 120)
}

function removeTag(tag: string) {
  chips.value = chips.value.filter((t) => t !== tag)
  if (props.shown.includes(tag)) {
    emit('update:shown', props.shown.filter((t) => t !== tag))
  }
}

function toggleShown(tag: string) {
  const shown = props.shown
  if (shown.includes(tag)) {
    emit('update:shown', shown.filter((t) => t !== tag))
    return
  }
  if (shown.length >= 3) return   // 格子上最多显示 3 个标签
  emit('update:shown', [...shown, tag])
}
</script>

<template>
  <div class="relative">
    <div
      ref="listEl"
      class="tag-editor cursor-text rounded-[10px] border"
      :class="compact ? '!rounded-lg !px-1.5 !py-0.5' : ''"
      style="border-color: var(--line-strong); background: rgba(255,255,255,.035)"
      @click="focusInput"
    >
      <span v-for="(tag, i) in chips" :key="tag"
            data-tag-chip
            class="chip chip-tag tag-drag !px-1.5 !text-[10.5px] !py-0.5"
            :class="{ 'tag-dragging': drag && drag.from === i,
                      'tag-drop-target': dropIndex === i && drag && drag.from !== i }"
            :title="'拖动可排序：' + tag"
            @pointerdown="startDrag(i, $event)">
        <button type="button" class="tag-eye" :title="shown.includes(tag) ? '在格子上显示：开' : '在格子上显示：关'"
                @pointerdown.stop @click.stop="toggleShown(tag)">
          <Eye v-if="shown.includes(tag)" :size="10" />
          <EyeOff v-else :size="10" />
        </button>
        <span class="tag-name">#{{ tag }}</span>
        <button type="button" class="tag-chip-x" :title="'删除 ' + tag"
                @pointerdown.stop @click.stop="removeTag(tag)">
          <X :size="10" />
        </button>
      </span>
      <input
        ref="inputEl"
        v-model="draft"
        class="tag-input"
        :placeholder="chips.length ? '' : placeholder"
        @keydown="onKeydown"
        @focus="focusOpen = true"
        @blur="handleBlur"
      />
    </div>

    <!-- 建议列表 -->
    <div
      v-if="focusOpen && shown.length"
      class="glass-strong absolute z-40 mt-1 flex max-w-full flex-wrap gap-1 rounded-xl p-1.5"
    >
      <button v-for="s in shown" :key="s" type="button"
              class="chip chip-tag !cursor-pointer !px-2 !py-1 !text-[11px]"
              @mousedown.prevent="addToken(s, true)">
        <Plus :size="10" class="mr-0.5 inline" /> {{ s }}
      </button>
    </div>

    <!-- 跟手悬浮的标签副本 -->
    <Teleport to="body">
      <div v-if="drag" class="tag-float-chip"
           :style="{ left: (drag.x - drag.dx) + 'px', top: (drag.y - drag.dy) + 'px', width: drag.w + 'px' }">
        #{{ drag.label }}
      </div>
    </Teleport>
  </div>
</template>