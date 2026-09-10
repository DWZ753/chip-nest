<script setup lang="ts">
import { computed } from 'vue'
import { Check, ChevronDown } from '@lucide/vue'
import {
  Listbox, ListboxButton, ListboxOption, ListboxOptions,
} from '@headlessui/vue'

// 通用玻璃下拉：面板 Teleport 到 body，避免被滚动/裁剪容器切掉
export interface SelectOption {
  value: string | number
  label: string
}

const props = withDefaults(defineProps<{
  modelValue: string | number | null
  options: SelectOption[]
  placeholder?: string
  disabled?: boolean
}>(), { placeholder: '请选择', disabled: false })

const emit = defineEmits<{
  (e: 'update:modelValue', value: string | number | null): void
}>()

const current = computed({
  get: () => props.modelValue ?? '',
  set: (v: string | number) => emit('update:modelValue', v),
})

const selectedLabel = computed(() =>
  props.options.find((o) => String(o.value) === String(props.modelValue))?.label
  ?? props.placeholder,
)
const hasValue = computed(() =>
  props.modelValue !== null && props.modelValue !== undefined && props.modelValue !== '')

// 面板位置：按触发按钮的视口坐标定位，必要时向上翻转
const panel = { left: 0, top: 0, width: 160, maxH: 240 }
function place(ev: Event) {
  const el = ev.currentTarget as HTMLElement | null
  if (!el) return
  const r = el.getBoundingClientRect()
  const below = window.innerHeight - r.bottom - 10
  const above = r.top - 10
  const up = below < 200 && above > below
  const maxH = Math.max(140, Math.min(280, up ? above : below))
  panel.left = r.left
  panel.width = Math.max(r.width, 150)
  panel.maxH = maxH
  panel.top = up ? r.top - maxH - 6 : r.bottom + 6
}
</script>

<template>
  <Listbox v-model="current" :disabled="disabled" as="div" v-slot="{ open }">
    <ListboxButton
      class="input flex items-center justify-between gap-1 !py-2 text-left disabled:opacity-50"
      :style="hasValue ? 'background-image: none' : 'color: var(--text-faint); background-image: none'"
      @click="place"
      @keydown.enter="place"
      @keydown.space="place"
      @keydown.up="place"
      @keydown.down="place"
    >
      <span class="truncate">{{ selectedLabel }}</span>
      <ChevronDown :size="13" class="ml-1 flex-shrink-0 opacity-60" />
    </ListboxButton>

    <Teleport to="body">
      <ListboxOptions
        v-if="open"
        static
        class="glass-strong fixed z-[300] overflow-y-auto rounded-xl p-1"
        :style="{ left: panel.left + 'px', top: panel.top + 'px', width: panel.width + 'px', maxHeight: panel.maxH + 'px' }"
      >
        <ListboxOption
          v-for="opt in options" :key="String(opt.value)" :value="opt.value" as="template"
          v-slot="{ active, selected }"
        >
          <li
            class="flex cursor-pointer select-none items-center gap-2 rounded-lg px-2.5 py-1.5 text-[12.5px]"
            :style="active ? 'background: var(--accent-dim)' : ''"
          >
            <span class="flex-1 truncate" :style="selected ? 'color: var(--accent-ink); font-weight: 700' : ''">
              {{ opt.label }}
            </span>
            <Check v-if="selected" :size="13" style="color: var(--accent)" />
          </li>
        </ListboxOption>
      </ListboxOptions>
    </Teleport>
  </Listbox>
</template>
