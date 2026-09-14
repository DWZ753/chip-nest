<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { Plus, X } from '@lucide/vue'

// 统一 chip 列表编辑器：系统字段（value/package/mpn/supplier）与自定义标签（#name）
// 在同一条可拖动列表里；每项都有眼睛开关控制是否显示在格子上，标签额外可删除。
const props = withDefaults(defineProps<{
  modelValue: string[]              // items 模式：统一 token；tags 模式：纯标签名
  mode?: 'items' | 'tags'
  shown?: string[]
  fieldLabels?: Record<string, string>
  suggestions?: string[]
  placeholder?: string
  compact?: boolean
  /** true=调整顺序（只拖拽）；false=点按切换是否显示 */
  adjust?: boolean
}>(), {
  mode: 'tags',
  shown: () => [],
  fieldLabels: () => ({}),
  suggestions: () => [],
  placeholder: '输入后回车添加',
  compact: false,
  adjust: false,
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: string[]): void
  (e: 'update:shown', value: string[]): void
}>()

const draft = ref('')
const inputEl = ref<HTMLInputElement | null>(null)
const listEl = ref<HTMLElement | null>(null)
const focusOpen = ref(false)
const adding = ref(false)

// ---------- token 与外部值的互转 ----------
const tokens = computed<string[]>(() => props.mode === 'tags'
  ? props.modelValue.map((n) => '#' + n)
  : props.modelValue)
const shownTokens = computed<string[]>(() => props.mode === 'tags'
  ? props.shown.map((n) => '#' + n)
  : props.shown)

function emitTokens(next: string[]) {
  emit('update:modelValue', props.mode === 'tags'
    ? next.map((t) => t.replace(/^#/, ''))
    : next)
}
function emitShownTokens(next: string[]) {
  emit('update:shown', props.mode === 'tags'
    ? next.map((t) => t.replace(/^#/, ''))
    : next)
}

const canDrag = computed(() => props.adjust || props.mode === 'tags')
const canToggle = computed(() => props.mode === 'items' && !props.adjust)
const showDelete = computed(() => !props.adjust)

const isTag = (token: string) => token.startsWith('#')
const tagName = (token: string) => token.replace(/^#/, '')
const labelOf = (token: string) => isTag(token)
  ? '#' + tagName(token)
  : (props.fieldLabels[token] ?? token)

// ---------- 显示开关 ----------
function toggleShown(token: string) {
  const shown = shownTokens.value
  if (shown.includes(token)) {
    emitShownTokens(shown.filter((t) => t !== token))
    return
  }
  if (isTag(token) && shown.filter(isTag).length >= 3) return  // 标签最多显示 3 个
  emitShownTokens([...shown, token])
}

function onChipClick(token: string) {
  if (canToggle.value) toggleShown(token)
}

function removeToken(token: string) {
  emitTokens(tokens.value.filter((t) => t !== token))
  if (shownTokens.value.includes(token)) {
    emitShownTokens(shownTokens.value.filter((t) => t !== token))
  }
}

function addTag(raw: string, atFront = false) {
  const name = raw.trim().replace(/^#/, '').slice(0, 20)
  if (!name) return
  const token = '#' + name
  if (tokens.value.includes(token)) { draft.value = ''; return }
  const next = atFront ? [token, ...tokens.value] : [...tokens.value, token]
  emitTokens(next.slice(0, 24))
  draft.value = ''
  focusOpen.value = false
}

function onKeydown(ev: KeyboardEvent) {
  if (ev.key === 'Enter' || ev.key === ',' || ev.key === '，' || ev.key === '、') {
    ev.preventDefault()
    addTag(draft.value)
    return
  }
  if (ev.key === 'Escape') {
    ev.preventDefault()
    closeAdd()
    return
  }
  if (ev.key === 'Backspace' && !draft.value) {
    const lastTag = [...tokens.value].reverse().find(isTag)
    if (lastTag) removeToken(lastTag)
  }
}

const suggestionList = computed(() => {
  const q = draft.value.trim().replace(/^#/, '').toLowerCase()
  const mine = new Set(tokens.value.filter(isTag).map(tagName))
  return props.suggestions.filter((s) => !mine.has(s)
    && (!q || s.toLowerCase().includes(q))).slice(0, 8)
})

function focusInput() {
  if (!adding.value) return
  nextTick(() => inputEl.value?.focus())
}

function openAdd() {
  adding.value = true
  focusOpen.value = true
  nextTick(() => inputEl.value?.focus())
}

function closeAdd() {
  adding.value = false
  focusOpen.value = false
  draft.value = ''
}

function handleBlur() {
  window.setTimeout(() => {
    if (draft.value.trim()) addTag(draft.value)
    closeAdd()
  }, 120)
}

// ---------- 拖动排序（跟手悬浮 + 插槽线） ----------
interface DragState { from: number; label: string; dx: number; dy: number; w: number; x: number; y: number; startX: number; startY: number }
const drag = ref<DragState | null>(null)
const dropSlot = ref(-1)
const moved = ref(false)

function chipNodes(): HTMLElement[] {
  const nodes = listEl.value?.querySelectorAll<HTMLElement>('[data-chip]') ?? []
  return Array.from(nodes)
}

function startDrag(index: number, ev: PointerEvent) {
  if (ev.button !== 0 || !canDrag.value) return
  const el = ev.currentTarget as HTMLElement
  const r = el.getBoundingClientRect()
  drag.value = {
    from: index, label: labelOf(tokens.value[index]),
    dx: ev.clientX - r.left, dy: ev.clientY - r.top, w: r.width,
    x: ev.clientX, y: ev.clientY, startX: ev.clientX, startY: ev.clientY,
  }
  dropSlot.value = index
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
  if (!moved.value && Math.hypot(ev.clientX - d.startX, ev.clientY - d.startY) > 4) {
    moved.value = true
  }
  // 插槽位置：指针越过多少个 chip 的中心，就插在第几个位置（支持最左/最右）
  let slot = 0
  for (const node of chipNodes()) {
    const r = node.getBoundingClientRect()
    if (ev.clientX > r.left + r.width / 2) slot += 1
  }
  dropSlot.value = slot
}

function endDrag() {
  window.removeEventListener('pointermove', onMove)
  window.removeEventListener('pointerup', endDrag)
  window.removeEventListener('pointercancel', endDrag)
  const d = drag.value
  const slot = dropSlot.value
  const wasMoved = moved.value
  drag.value = null
  dropSlot.value = -1
  moved.value = false
  if (!d || !wasMoved) return
  const list = [...tokens.value]
  const [item] = list.splice(d.from, 1)
  const insertAt = slot > d.from ? slot - 1 : slot
  list.splice(Math.max(0, Math.min(list.length, insertAt)), 0, item)
  emitTokens(list)
}
</script>

<template>
  <div class="relative">
    <div ref="listEl" class="tag-editor cursor-text rounded-[10px] border"
         :class="[compact ? '!rounded-lg !px-1.5 !py-0.5' : '', adjust ? 'adjusting' : '']"
         style="border-color: var(--line-strong); background: rgba(255,255,255,.035)"
         @click="focusInput">
      <template v-for="(token, i) in tokens" :key="token">
        <span v-if="dropSlot === i" class="tag-insert-line" />
        <span data-chip
              class="chip !px-1.5 !text-[10.5px] !py-0.5"
              :class="[isTag(token) ? 'chip-tag' : 'chip-field',
                       shownTokens.includes(token) ? 'chip-on' : 'chip-off',
                       { 'tag-drag': canDrag, 'tag-pick': canToggle,
                         'tag-dragging': drag && drag.from === i }]"
              @click="onChipClick(token)"
              :title="adjust ? '拖动调整顺序' : (isTag(token) ? '点按切换显示；× 删除' : '点按切换是否显示')"
              @pointerdown="startDrag(i, $event)">
          <span class="tag-name">{{ labelOf(token) }}</span>
          <button v-if="isTag(token) && showDelete" type="button" class="tag-chip-x"
                  :title="'删除 ' + tagName(token)"
                  @pointerdown.stop @click.stop="removeToken(token)">
            <X :size="10" />
          </button>
        </span>
      </template>
      <span v-if="dropSlot === tokens.length" class="tag-insert-line" />
      <button v-if="!adjust" type="button" class="chip tag-add-btn !px-1.5 !py-0.5"
              title="添加标签" @click.stop="openAdd">
        <Plus :size="11" /> 添加
      </button>
    </div>

    <!-- 添加标签：独立输入区（不挤在标签行里） -->
    <div v-if="adding" class="mt-1.5">
      <input ref="inputEl" v-model="draft" class="input !py-1.5 text-[12.5px]"
             :placeholder="placeholder"
             @keydown="onKeydown" @focus="focusOpen = true" @blur="handleBlur" />
    </div>

    <div v-if="focusOpen && suggestionList.length"
         class="glass-strong absolute z-40 mt-1 flex max-w-full flex-wrap gap-1 rounded-xl p-1.5">
      <button v-for="s in suggestionList" :key="s" type="button"
              class="chip chip-tag !cursor-pointer !px-2 !py-1 !text-[11px]"
              @mousedown.prevent="addTag(s, true)">
        <Plus :size="10" class="mr-0.5 inline" /> {{ s }}
      </button>
    </div>

    <Teleport to="body">
      <div v-if="drag" class="tag-float-chip"
           :style="{ left: (drag.x - drag.dx) + 'px', top: (drag.y - drag.dy) + 'px', width: drag.w + 'px' }">
        {{ drag.label }}
      </div>
    </Teleport>
  </div>
</template>