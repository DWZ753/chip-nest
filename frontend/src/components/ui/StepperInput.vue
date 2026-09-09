<script setup lang="ts">
import { Minus, Plus } from '@lucide/vue'

const props = withDefaults(defineProps<{
  modelValue: number
  min?: number
  max?: number
  step?: number
  disabled?: boolean
}>(), { min: 0, max: 999999, step: 1, disabled: false })

const emit = defineEmits<{ (e: 'update:modelValue', value: number): void }>()

function clamp(v: number): number {
  return Math.min(props.max, Math.max(props.min, Math.round(v * 100) / 100))
}

function add(delta: number) {
  emit('update:modelValue', clamp((props.modelValue || 0) + delta))
}

function onInput(ev: Event) {
  const raw = (ev.target as HTMLInputElement).value
  const num = Number.parseFloat(raw)
  emit('update:modelValue', Number.isNaN(num) ? props.min : clamp(num))
}
</script>

<template>
  <div class="flex items-stretch overflow-hidden rounded-[10px] border"
       :style="{ borderColor: 'var(--line-strong)' }">
    <button type="button" class="stepper-btn" :disabled="disabled || modelValue <= min" @click="add(-step)">
      <Minus :size="12" />
    </button>
    <input type="number" class="num w-full min-w-0 border-0 text-center !rounded-none !border-x-0"
           :value="modelValue" :disabled="disabled" :min="min" :max="max" :step="step"
           @input="onInput" />
    <button type="button" class="stepper-btn" :disabled="disabled || modelValue >= max" @click="add(step)">
      <Plus :size="12" />
    </button>
  </div>
</template>

<style scoped>
.stepper-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  color: var(--text-dim);
  background: var(--surface);
  cursor: pointer;
  transition: color 0.15s, background 0.15s;
}
.stepper-btn:hover:not(:disabled) { color: var(--accent); background: var(--accent-dim); }
.stepper-btn:disabled { opacity: 0.35; cursor: not-allowed; }
input[type='number'] { background: transparent; }
</style>
