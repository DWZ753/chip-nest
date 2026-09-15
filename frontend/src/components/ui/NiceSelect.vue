<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { Check, ChevronDown } from '@lucide/vue'

// 自绘玻璃下拉：不依赖第三方弹出的定位/裁剪逻辑，面板固定定位在触发按钮旁
export interface SelectOption {
  value: string | number
  label: string
}

const props = withDefaults(defineProps<{
  modelValue: string | number | null
  options: SelectOption[]
  placeholder?: string
  disabled?: boolean
}>(), { placeholder: '未选择', disabled: false })

const emit = defineEmits<{
  (e: 'update:modelValue', value: string | number | null): void
}>()

const open = ref(false)
const btn = ref<HTMLButtonElement | null>(null)
const panelEl = ref<HTMLElement | null>(null)
const panel = ref({ left: 0, top: 0, width: 160, maxH: 240 })

const selectedLabel = computed(() =>
  props.options.find((o) => String(o.value) === String(props.modelValue))?.label
  ?? props.placeholder,
)
const hasValue = computed(() =>
  props.modelValue !== null && props.modelValue !== undefined && props.modelValue !== '')

function place() {
  const el = btn.value
  if (!el) return
  const r = el.getBoundingClientRect()
  const below = window.innerHeight - r.bottom - 10
  const above = r.top - 10
  const up = below < 200 && above > below
  const maxH = Math.max(140, Math.min(280, up ? above : below))
  panel.value = {
    left: r.left,
    width: Math.max(r.width, 150),
    maxH,
    top: up ? Math.max(6, r.top - maxH - 6) : r.bottom + 6,
  }
}

function onDocClick(ev: MouseEvent) {
  const t = ev.target as Node | null
  if (t && (btn.value?.contains(t) || panelEl.value?.contains(t))) return
  close()
}

function onKeydown(ev: KeyboardEvent) {
  if (ev.key === 'Escape') close()
}

function openPanel() {
  if (props.disabled) return
  open.value = true
  place()
  window.addEventListener('click', onDocClick, true)
  window.addEventListener('keydown', onKeydown)
  window.addEventListener('resize', place)
  window.addEventListener('scroll', place, true)
}

function close() {
  open.value = false
  window.removeEventListener('click', onDocClick, true)
  window.removeEventListener('keydown', onKeydown)
  window.removeEventListener('resize', place)
  window.removeEventListener('scroll', place, true)
}

function toggle() {
  if (open.value) close()
  else openPanel()
}

function choose(opt: SelectOption) {
  emit('update:modelValue', opt.value)
  close()
}

onBeforeUnmount(close)
</script>

<template>
  <div class="relative">
    <button
      ref="btn"
      type="button"
      class="input flex w-full items-center justify-between gap-1 !py-2 text-left"
      :style="hasValue ? 'background-image: none' : 'color: var(--text-faint); background-image: none'"
      :disabled="disabled"
      @click="toggle"
    >
      <span class="truncate">{{ selectedLabel }}</span>
      <ChevronDown :size="13" class="ml-1 flex-shrink-0 opacity-60 transition-transform"
                   :style="open ? 'transform: rotate(180deg)' : ''" />
    </button>

    <Teleport to="body">
      <div
        v-if="open"
        ref="panelEl"
        class="glass-strong fixed z-[300] overflow-y-auto rounded-xl p-1"
        :style="{ left: panel.left + 'px', top: panel.top + 'px', width: panel.width + 'px', maxHeight: panel.maxH + 'px' }"
      >
        <button
          v-for="opt in options"
          :key="String(opt.value)"
          type="button"
          class="flex w-full cursor-pointer items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-[12.5px]"
          :style="String(opt.value) === String(modelValue)
            ? 'color: var(--accent-ink); font-weight: 700; background: var(--accent-dim)'
            : ''"
          @mouseenter="($event.currentTarget as HTMLElement).style.background = 'var(--accent-dim)'"
          @mouseleave="($event.currentTarget as HTMLElement).style.background = String(opt.value) === String(modelValue) ? 'var(--accent-dim)' : ''"
          @click="choose(opt)"
        >
          <span class="flex-1 truncate">{{ opt.label }}</span>
          <Check v-if="String(opt.value) === String(modelValue)" :size="13" style="color: var(--accent)" />
        </button>
        <div v-if="!options.length" class="px-2.5 py-1.5 text-[12px]" style="color: var(--text-faint)">
          无可选项
        </div>
      </div>
    </Teleport>
  </div>
</template>
