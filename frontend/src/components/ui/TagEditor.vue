<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { Plus, X } from '@lucide/vue'

// Steam/B站式多标签输入：回车/逗号/顿号添加，chip 可删，可给建议标签
const props = withDefaults(defineProps<{
  modelValue: string[]
  suggestions?: string[]
  placeholder?: string
  compact?: boolean
}>(), { suggestions: () => [], placeholder: '输入后回车添加', compact: false })

const emit = defineEmits<{ (e: 'update:modelValue', value: string[]): void }>()
const draft = ref('')
const inputEl = ref<HTMLInputElement | null>(null)
const focusOpen = ref(false)

const chips = computed({
  get: () => props.modelValue,
  set: (v: string[]) => emit('update:modelValue', v),
})

function addToken(raw: string, useSuggestion = false) {
  const item = (useSuggestion ? raw : raw).trim().slice(0, 20)
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

// ---------- 拖拽排序 ----------
const dragIndex = ref(-1)
const dropIndex = ref(-1)

function onDragStart(index: number, ev: DragEvent) {
  dragIndex.value = index
  dropIndex.value = index
  ev.dataTransfer?.setData('text/plain', String(index))
  if (ev.dataTransfer) ev.dataTransfer.effectAllowed = 'move'
}

function onDragOver(index: number, ev: DragEvent) {
  ev.preventDefault()
  if (ev.dataTransfer) ev.dataTransfer.dropEffect = 'move'
  dropIndex.value = index
}

function onDrop(index: number, ev: DragEvent) {
  ev.preventDefault()
  const from = dragIndex.value
  dragIndex.value = -1
  dropIndex.value = -1
  if (from < 0 || from === index) return
  const list = [...chips.value]
  const [moved] = list.splice(from, 1)
  list.splice(index, 0, moved)
  chips.value = list
}

function onDragEnd() {
  dragIndex.value = -1
  dropIndex.value = -1
}

function handleBlur() {
  window.setTimeout(() => {
    focusOpen.value = false
    if (draft.value.trim()) addToken(draft.value)
  }, 120)
}

function removeTag(tag: string) {
  chips.value = chips.value.filter((t) => t !== tag)
}
</script>

<template>
  <div class="relative">
    <div
      class="tag-editor cursor-text rounded-[10px] border"
      :class="compact ? '!rounded-lg !px-1.5 !py-0.5' : ''"
      style="border-color: var(--line-strong); background: rgba(255,255,255,.035)"
      @click="focusInput"
    >
      <span v-for="(tag, i) in chips" :key="tag"
            class="chip chip-tag tag-drag !px-1.5 !text-[10.5px] !py-0.5"
            :class="{ 'tag-dragging': dragIndex === i, 'tag-drop-target': dropIndex === i && dragIndex !== i }"
            draggable="true"
            :title="'拖动可调整顺序：' + tag"
            @dragstart="onDragStart(i, $event)"
            @dragover="onDragOver(i, $event)"
            @drop="onDrop(i, $event)"
            @dragend="onDragEnd">
        #{{ tag }}
        <button type="button" class="tag-chip-x" :title="'删除 ' + tag" @click.stop="removeTag(tag)">
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
    <!-- 建议列表：B站式可选现成标签 -->
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
  </div>
</template>