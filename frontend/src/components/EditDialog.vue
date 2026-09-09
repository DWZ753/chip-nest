<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import {
  Dialog, DialogPanel, DialogTitle, TransitionChild, TransitionRoot,
} from '@headlessui/vue'
import { Minus, Pencil, Plus, Trash2, X } from '@lucide/vue'

import { api, ApiError } from '../api/client'
import type { ComponentItem, LayoutConfig } from '../api/types'
import { useBinsStore, type BinPosition } from '../stores/bins'
import NiceSelect, { type SelectOption } from './ui/NiceSelect.vue'
import TagEditor from './ui/TagEditor.vue'

const props = defineProps<{
  open: boolean
  comp: ComponentItem | null      // null = 新建
  createPos: BinPosition | null   // 新建时的落位
  layout: LayoutConfig
}>()

const emit = defineEmits<{ close: [] }>()
const bins = useBinsStore()

const isCreate = computed(() => props.comp === null)

const form = reactive({
  name: '',
  value: '',
  package: '',
  manufacturer_part: '',
  supplier_part: '',
  threshold: 5,
  zone: 1,
  layer: 1,
  slot: 0,
})
const tags = ref<string[]>([])
const displayTags = ref<string[]>([])
const tagSuggestions = computed(() => {
  const used = new Set(tags.value)
  const pool = new Set<string>()
  for (const c of bins.components) for (const t of c.tags ?? []) pool.add(t)
  return Array.from(pool).filter((t) => !used.has(t)).slice(0, 8)
})
const initQty = ref(0)
const amount = ref(1)
const localQty = ref(0)
const busy = ref(false)
const deleting = ref(false)
const errorMsg = ref<string | null>(null)
let deleteTimer: ReturnType<typeof setTimeout> | undefined

watch(
  () => [props.open, props.comp, props.createPos] as const,
  () => {
    if (!props.open) return
    errorMsg.value = null
    deleting.value = false
    amount.value = 1
    if (props.comp) {
      form.name = props.comp.name
      form.value = props.comp.value ?? ''
      form.package = props.comp.package ?? ''
      form.manufacturer_part = props.comp.manufacturer_part ?? ''
      form.supplier_part = props.comp.supplier_part ?? ''
      tags.value = [...(props.comp.tags ?? [])]
      displayTags.value = [...(props.comp.display_tags ?? [])]
      form.threshold = props.comp.threshold
      form.zone = props.comp.zone
      form.layer = props.comp.layer
      form.slot = props.comp.slot
      localQty.value = props.comp.quantity
    } else {
      const p = props.createPos ?? { zone: 1, layer: 1, slot: 0 }
      form.name = ''
      form.value = ''
      form.package = ''
      form.manufacturer_part = ''
      form.supplier_part = ''
      tags.value = []
      displayTags.value = []
      form.threshold = 5
      form.zone = p.zone
      form.layer = p.layer
      form.slot = p.slot
      initQty.value = 0
      localQty.value = 0
    }
  },
  { immediate: true },
)

const zoneOptions = computed<SelectOption[]>(() =>
  Array.from({ length: props.layout.zone_count }, (_, i) => ({
    value: i + 1, label: `第 ${i + 1} 区`,
  })))
const layerOptions = computed<SelectOption[]>(() =>
  Array.from({ length: props.layout.layer_count }, (_, i) => ({
    value: i + 1, label: `第 ${i + 1} 层`,
  })))
const slotOptions = computed<SelectOption[]>(() =>
  slots.value.map((s) => ({ value: s, label: String(s) })))

const slots = computed(() =>
  Array.from({ length: props.layout.row_count * props.layout.col_count }, (_, i) => i),
)

function fail(e: unknown) {
  errorMsg.value = e instanceof Error ? e.message : String(e)
}

function toggleDisplay(tag: string) {
  if (displayTags.value.includes(tag)) {
    displayTags.value = displayTags.value.filter((t) => t !== tag)
  } else if (displayTags.value.length < 3) {
    displayTags.value = [...displayTags.value, tag]
  }
}

async function save() {
  const name = form.name.trim()
  if (!name) { errorMsg.value = '请填写元件名称'; return }
  busy.value = true
  errorMsg.value = null
  try {
    if (isCreate.value) {
      const created = await api.createComponent({
        name: form.name.trim(),
        value: form.value.trim() || null,
        package: form.package.trim() || null,
        manufacturer_part: form.manufacturer_part.trim() || null,
        supplier_part: form.supplier_part.trim() || null,
        tags: [...tags.value],
        display_tags: [...displayTags.value],
        quantity: Math.max(0, initQty.value | 0),
        threshold: Math.max(0, form.threshold | 0),
        zone: form.zone, layer: form.layer, slot: form.slot,
      })
      bins.upsert(created)
      emit('close')
      return
    }
    const patch: Record<string, unknown> = {
      name,
      value: form.value.trim() || null,
      package: form.package.trim() || null,
      manufacturer_part: form.manufacturer_part.trim() || null,
      supplier_part: form.supplier_part.trim() || null,
      tags: [...tags.value],
      threshold: Math.max(0, form.threshold | 0),
    }
    const moved = form.zone !== props.comp!.zone || form.layer !== props.comp!.layer
      || form.slot !== props.comp!.slot
    if (moved) {
      patch.zone = form.zone
      patch.layer = form.layer
      patch.slot = form.slot
    }
    const updated = await api.patchComponent(props.comp!.id, patch)
    bins.upsert(updated)
    emit('close')
  } catch (e) { fail(e) } finally { busy.value = false }
}

async function stock(delta: number) {
  if (!props.comp || delta === 0) return
  busy.value = true
  errorMsg.value = null
  try {
    const n = Math.abs(amount.value | 0) || 1
    const updated = await bins.adjustStock(props.comp.id, Math.sign(delta) * n)
    localQty.value = updated.quantity
  } catch (e) {
    fail(e)
    if (e instanceof ApiError && e.available !== undefined) {
      errorMsg.value = `库存不足，当前剩余 ${e.available}`
    }
  } finally { busy.value = false }
}

async function remove() {
  if (!props.comp) return
  if (!deleting.value) {
    deleting.value = true
    window.clearTimeout(deleteTimer)
    deleteTimer = window.setTimeout(() => { deleting.value = false }, 3200)
    return
  }
  busy.value = true
  try {
    await bins.removeComponent(props.comp.id)
    emit('close')
  } catch (e) { fail(e) } finally { busy.value = false }
}

function close() {
  window.clearTimeout(deleteTimer)
  emit('close')
}
</script>

<template>
  <TransitionRoot :show="open" as="template">
    <Dialog as="div" class="relative z-50" @close="close">
      <TransitionChild
        as="template" enter="duration-200 ease-out" enter-from="opacity-0"
        leave="duration-150 ease-in" leave-to="opacity-0"
      >
        <div class="fixed inset-0 bg-black/25 backdrop-blur-[3px]" />
      </TransitionChild>

      <div class="fixed inset-0 overflow-y-auto">
        <div class="flex min-h-full items-center justify-center p-4">
          <TransitionChild
            as="template" enter="duration-200 ease-out"
            enter-from="opacity-0 translate-y-3 scale-95"
            enter-to="opacity-100 translate-y-0 scale-100"
            leave="duration-150 ease-in" leave-to="opacity-0 translate-y-3 scale-95"
          >
            <DialogPanel
              class="glass-strong w-full max-w-md rounded-3xl p-5"
            >
              <div class="mb-4 flex items-center gap-2">
                <div
                  class="grid h-8 w-8 place-items-center rounded-xl text-white"
                  style="background: linear-gradient(135deg, var(--accent-strong), var(--warm))"
                >
                  <Pencil v-if="!isCreate" :size="15" />
                  <Plus v-else :size="15" />
                </div>
                <DialogTitle class="text-base font-extrabold">
                  {{ isCreate ? '新建元件' : '编辑元件' }}
                </DialogTitle>
                <button class="icon-btn ml-auto !h-8 !w-8" @click="close"><X :size="16" /></button>
              </div>

              <div class="flex flex-col gap-3.5">
                <div>
                  <label class="field-label">名称</label>
                  <input v-model="form.name" class="input" maxlength="64"
                         placeholder="如 10k电阻 / 100nF电容 / LED指示灯" />
                </div>

                <div class="grid grid-cols-2 gap-3">
                  <div>
                    <label class="field-label">标称值</label>
                    <input v-model="form.value" class="input mono" maxlength="32"
                           placeholder="10k / 100nF / 22Ω" />
                  </div>
                  <div>
                    <label class="field-label">封装</label>
                    <input v-model="form.package" class="input mono" maxlength="32"
                           placeholder="0603 / 0805" />
                  </div>
                </div>

                <div class="grid grid-cols-2 gap-3">
                  <div>
                    <label class="field-label">厂商料号</label>
                    <input v-model="form.manufacturer_part" class="input mono"
                           maxlength="64" placeholder="例：CL05B104KB54PNC" />
                  </div>
                  <div>
                    <label class="field-label">供应商料号</label>
                    <input v-model="form.supplier_part" class="input mono"
                           maxlength="40" placeholder="例：C307331" />
                  </div>
                </div>

                <div>
                  <label class="field-label">格子标签（内部，用于搜索）</label>
                  <TagEditor v-model="tags" :suggestions="tagSuggestions"
                             placeholder="输入后回车，可加多个" />
                </div>
                <div v-if="tags.length">
                  <label class="field-label">显示在格子上的（挑 1–3 个，与名称一起）</label>
                  <div class="flex flex-wrap gap-1.5">
                    <button v-for="tag in tags" :key="tag" type="button"
                            class="chip !cursor-pointer !px-2.5 !py-1 !text-[11.5px]"
                            :class="displayTags.includes(tag) ? '' : 'opacity-45 hover:opacity-80'"
                            :style="displayTags.includes(tag)
                              ? 'background: linear-gradient(120deg, #7c6cf0, #8b8ef7); border-color: transparent; color: #fff'
                              : ''"
                            @click="toggleDisplay(tag)">
                      {{ tag }}
                    </button>
                  </div>
                  <div v-if="displayTags.length === 3" class="mt-1 text-[10.5px]"
                       style="color: var(--text-faint)">最多 3 个</div>
                </div>

                <!-- 位置 + 阈值 -->
                <div class="grid grid-cols-2 gap-3">
                  <div class="grid grid-cols-3 gap-2">
                    <div>
                      <label class="field-label">区</label>
                      <NiceSelect v-model="form.zone" :options="zoneOptions" />
                    </div>
                    <div>
                      <label class="field-label">层</label>
                      <NiceSelect v-model="form.layer" :options="layerOptions" />
                    </div>
                    <div>
                      <label class="field-label">格</label>
                      <NiceSelect v-model="form.slot" :options="slotOptions" />
                    </div>
                  </div>
                  <div>
                    <label class="field-label">补货阈值</label>
                    <input v-model.number="form.threshold" class="input num" type="number" min="0" max="9999" />
                  </div>
                </div>

                <!-- 新建：初始库存 -->
                <div v-if="isCreate">
                  <label class="field-label">初始库存</label>
                  <input v-model.number="initQty" class="input num" type="number" min="0" max="99999" />
                </div>

                <div v-if="errorMsg" class="rounded-xl px-3 py-2 text-[12.5px] font-semibold"
                     style="background: color-mix(in srgb, var(--danger) 14%, transparent); color: var(--danger)">
                  {{ errorMsg }}
                </div>

                <!-- 入出库（编辑态） -->
                <template v-if="!isCreate">
                  <div class="flex items-center justify-between rounded-2xl px-3 py-2.5"
                       style="background: var(--panel); border: 1px solid var(--line)">
                    <span class="text-xs font-semibold" style="color: var(--text-dim)">当前库存</span>
                    <span class="num text-xl font-black" style="color: var(--accent-ink)">{{ localQty }}</span>
                    <div class="flex items-center gap-1.5">
                      <input v-model.number="amount" class="input !w-16 !px-2 num text-center" type="number" min="1" max="9999" />
                    </div>
                  </div>
                  <div class="grid grid-cols-2 gap-2.5">
                    <button class="btn" :disabled="busy" @click="stock(-1)">
                      <Minus :size="15" /> 出库
                    </button>
                    <button class="btn btn-primary" :disabled="busy" @click="stock(1)">
                      <Plus :size="15" /> 入库
                    </button>
                  </div>
                </template>

                <div class="mt-2 flex items-center gap-2">
                  <button v-if="!isCreate" class="btn btn-danger" :disabled="busy" @click="remove">
                    <Trash2 :size="14" /> {{ deleting ? '确认删除？' : '删除' }}
                  </button>
                  <div class="flex-1" />
                  <button class="btn btn-ghost" @click="close">取消</button>
                  <button class="btn btn-primary" :disabled="busy || (isCreate && !form.name.trim())" @click="save">
                    {{ isCreate ? '建档' : '保存' }}
                  </button>
                </div>
              </div>
            </DialogPanel>
          </TransitionChild>
        </div>
      </div>
    </Dialog>
  </TransitionRoot>
</template>