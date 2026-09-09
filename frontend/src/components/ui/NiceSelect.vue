<script setup lang="ts">
import { computed } from 'vue'
import { Check, ChevronDown } from '@lucide/vue'
import {
  Listbox, ListboxButton, ListboxOption, ListboxOptions,
} from '@headlessui/vue'

// 通用玻璃下拉：替代原生 select（原生弹出菜单无法美化）
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
</script>

<template>
  <Listbox v-model="current" :disabled="disabled">
    <div class="relative">
      <ListboxButton
        class="input flex items-center justify-between gap-1 !py-2 text-left disabled:opacity-50"
        :style="hasValue ? 'background-image: none' : 'color: var(--text-faint); background-image: none'"
      >
        <span class="truncate">{{ selectedLabel }}</span>
        <ChevronDown :size="13" class="ml-1 flex-shrink-0 opacity-60" />
      </ListboxButton>
      <Transition
        enter="transition duration-100 ease-out"
        enter-from="opacity-0 scale-95"
        enter-to="opacity-100 scale-100"
        leave="transition duration-75 ease-in"
        leave-from="opacity-100 scale-100"
        leave-to="opacity-0 scale-95"
      >
        <ListboxOptions
          class="glass-strong absolute z-50 mt-1 max-h-64 w-full min-w-[140px] overflow-y-auto rounded-xl p-1"
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
      </Transition>
    </div>
  </Listbox>
</template>