<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import {
  Dialog, DialogPanel, DialogTitle, TransitionChild, TransitionRoot,
} from '@headlessui/vue'
import { Check, Link2, Minus, Pencil, Plus, Sparkles, Trash2, X } from '@lucide/vue'

import { api, ApiError } from '../api/client'
import type { ComponentItem, LayoutConfig, LookupCandidate, SlotRef } from '../api/types'
import { useBinsStore, zoneGrid, zoneLayers, type BinPosition } from '../stores/bins'
import { suggestThreshold } from '../utils/stock'
import { ArrowLeftRight } from '@lucide/vue'
import NiceSelect, { type SelectOption } from './ui/NiceSelect.vue'
import TagEditor from './ui/TagEditor.vue'
import StepperInput from './ui/StepperInput.vue'

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
// 统一列表：items = 显示顺序 token（字段名或 "#标签"），shownItems = 其中要显示的
const items = ref<string[]>([])
const shownItems = ref<string[]>([])
const adjustMode = ref(false)
const FIELD_LABELS: Record<string, string> = {
  value: '标称值',
  package: '封装',
  mpn: '厂商料号',
  supplier: '供应商料号',
}
const FIELD_KEYS = ['value', 'package', 'mpn', 'supplier']

const tagNames = computed(() => items.value.filter((t) => t.startsWith('#')).map((t) => t.slice(1)))
const tagSuggestions = computed(() => {
  const used = new Set(tagNames.value)
  const pool = new Set<string>()
  for (const c of bins.components) for (const t of c.tags ?? []) pool.add(t)
  return Array.from(pool).filter((t) => !used.has(t)).slice(0, 8)
})
const initQty = ref(0)
const amount = ref(1)

// ---- 占用格子：同一物料拆到多个格子存放 ----
const slotBusy = ref(false)
const liveComp = computed<ComponentItem | null>(
  () => bins.components.find((c) => c.id === props.comp?.id) ?? props.comp,
)
const freeSlotOptions = computed<SelectOption[]>(() =>
  bins.freeSlots().slice(0, 300).map((p) => ({
    value: `${p.zone}:${p.layer}:${p.slot}`,
    label: `${p.zone}区/${p.layer}层/${p.slot}格`,
  })))

async function addSlotFromPicker(key: string | number | null) {
  const id = liveComp.value?.id
  if (!id || typeof key !== 'string' || !key) return
  const [zone, layer, slot] = key.split(':').map(Number)
  slotBusy.value = true
  errorMsg.value = null
  try {
    await bins.addSlot(id, { zone, layer, slot })
  } catch (e) { fail(e) } finally { slotBusy.value = false }
}

async function dropSlot(s: SlotRef) {
  const id = liveComp.value?.id
  if (!id) return
  slotBusy.value = true
  errorMsg.value = null
  try {
    await bins.removeSlot(id, s)
  } catch (e) { fail(e) } finally { slotBusy.value = false }
}
// 阈值可自动跟随初始库存（默认自动）：入库量改一次、阈值跟着同步一次；
// 任何时候手动改阈值都会切到「手动」，两边不打架；再点回「自动」立刻同步一次。
const autoThreshold = ref(true)

watch(initQty, (qty) => {
  if (!autoThreshold.value) return
  form.threshold = suggestThreshold(qty)
})

function onThresholdEdit(value: number) {
  form.threshold = value
  autoThreshold.value = false
}

function toggleAutoThreshold() {
  autoThreshold.value = !autoThreshold.value
  if (autoThreshold.value) form.threshold = suggestThreshold(initQty.value)
}
const localQty = ref(0)

// ---- 联网识别：输入料号/描述 → 自动填 名称/值/封装/厂商料号/供应商编号 ----
const lookupText = ref('')
const lookupBusy = ref(false)
const lookupError = ref<string | null>(null)
const lookupNote = ref<string | null>(null)
const candidates = ref<LookupCandidate[]>([])
const datasheet = ref('')
const appliedParams = ref<Record<string, string>>({})
// 当前选中的候选下标（-1=没选）：点候选要立刻看到选中的是哪一条
const pickedIndex = ref(-1)

function resetLookup(seed = '') {
  lookupText.value = seed
  lookupBusy.value = false
  lookupError.value = null
  lookupNote.value = null
  candidates.value = []
  datasheet.value = ''
  appliedParams.value = {}
  pickedIndex.value = -1
}

function applyCandidate(c: LookupCandidate, index = -1) {
  // 换一条候选就把五个字段整体刷新一遍（该条没有的字段清空），
  // 否则会出现"点了另一条但界面没变"的错觉
  form.name = c.name || ''
  form.value = c.value || ''
  form.package = c.package || ''
  form.manufacturer_part = c.mpn || ''
  form.supplier_part = c.lcsc || ''
  pickedIndex.value = index
  datasheet.value = c.datasheet || ''
  appliedParams.value = c.params ?? {}
  const tag = [c.lcsc, c.mpn].filter(Boolean).join(' ')
  lookupNote.value = tag ? `已填入 ${tag}` : '已填入'
  lookupError.value = null
}

async function runLookup() {
  const text = lookupText.value.trim()
  if (!text || lookupBusy.value) return
  lookupBusy.value = true
  lookupError.value = null
  lookupNote.value = null
  candidates.value = []
  try {
    const res = await api.lookupAutofill(text)
    candidates.value = res.candidates ?? []
    if (candidates.value.length) {
      applyCandidate(candidates.value[0], 0)
      if (candidates.value.length > 1) {
        lookupNote.value = (lookupNote.value ?? '') + `，共 ${candidates.value.length} 个候选`
      }
    } else {
      lookupError.value = res.online ? '没查到对应元件' : '联网失败'
    }
  } catch (e) {
    lookupError.value = e instanceof Error ? e.message : String(e)
  } finally {
    lookupBusy.value = false
  }
}
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
    adjustMode.value = false
    amount.value = 1
    const comp = props.comp
    // 编辑时用现有的料号/编号当识别输入初值，省得再打一遍
    resetLookup(comp ? (comp.manufacturer_part || comp.supplier_part || comp.name) : '')
    if (comp) {
      form.name = comp.name
      form.value = props.comp.value ?? ''
      form.package = props.comp.package ?? ''
      form.manufacturer_part = props.comp.manufacturer_part ?? ''
      form.supplier_part = props.comp.supplier_part ?? ''
      const order = (comp.card_items ?? []).length
        ? [...comp.card_items]
        : [...FIELD_KEYS, ...(comp.tags ?? []).map((t) => '#' + t)]
      for (const key of FIELD_KEYS) if (!order.includes(key)) order.unshift(key)
      for (const tag of comp.tags ?? []) {
        if (!order.includes('#' + tag)) order.push('#' + tag)
      }
      items.value = order
      shownItems.value = [
        ...FIELD_KEYS.filter((k) => (comp.display_fields ?? ['value', 'package']).includes(k)),
        ...(comp.display_tags ?? []).map((t) => '#' + t),
      ]
      form.threshold = props.comp.threshold
      autoThreshold.value = false  // 已有元件保留自己的阈值
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
      items.value = [...FIELD_KEYS]
      shownItems.value = ['value', 'package']
      form.threshold = 5
      form.zone = p.zone
      form.layer = p.layer
      form.slot = p.slot
      initQty.value = 0
      localQty.value = 0
      autoThreshold.value = true
    }
  },
  { immediate: true },
)

// 选项只用数字：列窄也能完整显示（区/层/格 表头已说明含义）
const zoneOptions = computed<SelectOption[]>(() =>
  Array.from({ length: props.layout.zone_count }, (_, i) => ({
    value: i + 1, label: String(i + 1),
  })))
// 层选项按「当前选中的区」的层数生成（各区层数可以不同）
const layerOptions = computed<SelectOption[]>(() =>
  Array.from({ length: zoneLayers(props.layout, form.zone) }, (_, i) => ({
    value: i + 1, label: String(i + 1),
  })))
const slotOptions = computed<SelectOption[]>(() =>
  slots.value.map((s) => ({ value: s, label: String(s) })))

// 格选项按“当前选中的区”的尺寸生成
const slots = computed(() => {
  const [rows, cols] = zoneGrid(props.layout, form.zone)
  return Array.from({ length: rows * cols }, (_, i) => i)
})

watch(
  () => form.zone,
  () => {
    const [rows, cols] = zoneGrid(props.layout, form.zone)
    if (form.slot >= rows * cols) form.slot = 0
    const layers = zoneLayers(props.layout, form.zone)
    if (form.layer > layers) form.layer = layers
  },
)

const urgency = computed(() => {
  const q = localQty.value
  const t = Math.max(1, form.threshold | 0)
  if (q <= 0) return { text: '缺货', color: 'var(--danger)', border: 'color-mix(in srgb, var(--danger) 55%, var(--line))' }
  if (q < t / 2) return { text: '告急', color: 'var(--danger)', border: 'color-mix(in srgb, var(--danger) 45%, var(--line))' }
  if (q < t) return { text: '偏低', color: 'var(--warn)', border: 'color-mix(in srgb, var(--warn) 50%, var(--line))' }
  return { text: '充足', color: 'var(--success)', border: 'var(--line)' }
})

function fail(e: unknown) {
  errorMsg.value = e instanceof Error ? e.message : String(e)
}

async function save() {
  const name = form.name.trim()
  if (!name) { errorMsg.value = '名称为空'; return }
  busy.value = true
  errorMsg.value = null
  try {
    if (isCreate.value) {
      const tagList = items.value.filter((t) => t.startsWith('#')).map((t) => t.slice(1))
      const fields = FIELD_KEYS.filter((k) => shownItems.value.includes(k))
      const shownTags = items.value
        .filter((t) => t.startsWith('#') && shownItems.value.includes(t))
        .map((t) => t.slice(1))
      const created = await api.createComponent({
        name: form.name.trim(),
        value: form.value.trim() || null,
        package: form.package.trim() || null,
        manufacturer_part: form.manufacturer_part.trim() || null,
        supplier_part: form.supplier_part.trim() || null,
        tags: tagList,
        display_tags: shownTags,
        display_fields: fields,
        card_items: [...items.value],
        quantity: Math.max(0, initQty.value | 0),
        threshold: Math.max(0, form.threshold | 0),
        zone: form.zone, layer: form.layer, slot: form.slot,
      })
      bins.upsert(created)
      emit('close')
      return
    }
    const tagList = items.value.filter((t) => t.startsWith('#')).map((t) => t.slice(1))
    const fields = FIELD_KEYS.filter((k) => shownItems.value.includes(k))
    const shownTags = items.value
      .filter((t) => t.startsWith('#') && shownItems.value.includes(t))
      .map((t) => t.slice(1))
    const patch: Record<string, unknown> = {
      name,
      value: form.value.trim() || null,
      package: form.package.trim() || null,
      manufacturer_part: form.manufacturer_part.trim() || null,
      supplier_part: form.supplier_part.trim() || null,
      tags: tagList,
      display_tags: shownTags,
      display_fields: fields,
      card_items: [...items.value],
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
                <!-- 联网识别：认料号/描述，填下面的栏位（离线也能手工填） -->
                <section class="rounded-2xl p-3" style="background: var(--panel); border: 1px solid var(--line)">
                  <div class="flex items-center gap-2">
                    <Sparkles :size="14" style="color: var(--accent)" />
                    <span class="text-[12.5px] font-extrabold">联网识别</span>
                  </div>
                  <div class="mt-2 flex items-center gap-2">
                    <input v-model="lookupText" class="input mono min-w-0 flex-1 !py-1.5" maxlength="80"
                           placeholder="10k 0603 ／ C14663 ／ STM32F103C8T6"
                           @keydown.enter="runLookup" />
                    <button class="btn btn-primary flex-shrink-0 whitespace-nowrap !px-3 !py-1.5 text-xs"
                            :disabled="lookupBusy || !lookupText.trim()" @click="runLookup">
                      {{ lookupBusy ? '查询中…' : '识别' }}
                    </button>
                  </div>

                  <div v-if="lookupNote" class="mt-1.5 text-[11.5px] font-semibold"
                       style="color: var(--success)">{{ lookupNote }}</div>
                  <div v-if="lookupError" class="mt-1.5 text-[11.5px] font-semibold"
                       style="color: var(--danger)">{{ lookupError }}</div>

                  <div v-if="Object.keys(appliedParams).length"
                       class="mt-2 flex flex-wrap gap-1">
                    <span v-for="(v, k) in appliedParams" :key="k" class="chip !px-1.5 !text-[10px]"
                          :title="String(k)">{{ k }} {{ v }}</span>
                  </div>
                  <div v-if="datasheet" class="mt-1.5 text-[11px]">
                    <a :href="datasheet" target="_blank" rel="noreferrer" style="color: var(--accent)">
                      查看数据手册
                    </a>
                  </div>

                  <div v-if="candidates.length > 1"
                       class="mt-2 flex max-h-44 flex-col gap-1 overflow-y-auto pr-1">
                    <button v-for="(c, i) in candidates" :key="(c.lcsc || 'x') + i"
                            class="rounded-xl px-2.5 py-1.5 text-left text-[11.5px] transition-colors"
                            :style="pickedIndex === i
                              ? 'border: 1.5px solid var(--accent); background: var(--accent-dim)'
                              : 'border: 1px solid var(--line)'"
                            @click="applyCandidate(c, i)">
                      <div class="flex items-center gap-2">
                        <Check v-if="pickedIndex === i" :size="12" style="color: var(--accent)" />
                        <span class="mono font-bold" style="color: var(--accent)">{{ c.lcsc || '—' }}</span>
                        <span class="truncate" :class="pickedIndex === i ? 'font-extrabold' : 'font-semibold'">{{ c.name }}</span>
                        <span class="num ml-auto flex-shrink-0" style="color: var(--text-faint)">存 {{ c.stock }}</span>
                      </div>
                      <div class="truncate" style="color: var(--text-dim)">
                        {{ c.mpn }}<span v-if="c.manufacturer"> · {{ c.manufacturer }}</span><span v-if="c.package"> · {{ c.package }}</span>
                      </div>
                    </button>
                  </div>
                </section>

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

                <div class="rounded-xl px-3 py-2.5"
                     style="background: var(--panel); border: 1px solid var(--line)">
                  <div class="mb-2 flex items-center gap-2">
                    <span class="field-label !mb-0">标签与显示</span>
                    <button type="button" class="btn ml-auto !px-2.5 !py-1 text-[11.5px]"
                            :class="adjustMode ? 'btn-primary' : ''"
                            :title="adjustMode ? '完成排序' : '进入排序状态'"
                            @click="adjustMode = !adjustMode">
                      <ArrowLeftRight :size="12" />
                      {{ adjustMode ? '完成调整' : '调整顺序' }}
                    </button>
                  </div>
                  <!-- 状态1（默认）：点按切换是否显示；状态2：只拖拽调整顺序 -->
                  <TagEditor mode="items" v-model="items" v-model:shown="shownItems"
                             :adjust="adjustMode"
                             :field-labels="FIELD_LABELS" :suggestions="tagSuggestions"
                             placeholder="输入后回车添加标签" />
                </div>

                <!-- 位置 + 阈值 -->
                <div class="grid grid-cols-[2.4fr_1fr] gap-3">
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
                    <div class="flex items-center gap-1.5">
                      <label class="field-label">补货阈值</label>
                      <button class="chip !cursor-pointer !px-2 !py-0.5 !text-[10.5px]"
                              :class="autoThreshold ? '' : 'opacity-55'"
                              :style="autoThreshold ? 'color: var(--accent); border-color: var(--accent)' : ''"
                              @click="toggleAutoThreshold">
                        {{ autoThreshold ? '自动' : '手动' }}
                      </button>
                    </div>
                    <StepperInput v-model="form.threshold" :min="0" :max="9999"
                                  @update:model-value="onThresholdEdit" />
                  </div>
                </div>

                <!-- 占用格子：同一物料放在多处 -->
                <section v-if="!isCreate" class="rounded-2xl p-3"
                         style="background: var(--panel); border: 1px solid var(--line)">
                  <div class="flex items-center gap-2 text-[12.5px] font-extrabold">
                    <Link2 :size="14" style="color: var(--accent-strong)" /> 占用格子
                  </div>
                  <div class="mt-2 flex flex-wrap items-center gap-1.5">
                    <span v-for="s in (liveComp?.slots ?? [])" :key="`${s.zone}:${s.layer}:${s.slot}`"
                          class="chip !px-1.5 !text-[10.5px]">
                      {{ s.zone }}区/{{ s.layer }}层/{{ s.slot }}格
                      <button class="ml-1 opacity-60 hover:opacity-100" :disabled="slotBusy"
                              @click="dropSlot(s)">×</button>
                    </span>
                    <span v-if="!(liveComp?.slots ?? []).length" class="text-[11.5px]"
                          style="color: var(--text-faint)">—</span>
                  </div>
                  <div class="mt-2">
                    <NiceSelect :model-value="''" :options="freeSlotOptions" :disabled="slotBusy"
                                placeholder="添加格子" @update:model-value="addSlotFromPicker" />
                  </div>
                </section>

                <!-- 新建：初始库存 -->
                <div v-if="isCreate" class="w-40">
                  <label class="field-label">初始库存</label>
                  <StepperInput v-model="initQty" :min="0" :max="99999" />
                </div>

                <div v-if="errorMsg" class="rounded-xl px-3 py-2 text-[12.5px] font-semibold"
                     style="background: color-mix(in srgb, var(--danger) 14%, transparent); color: var(--danger)">
                  {{ errorMsg }}
                </div>

                <!-- 入出库（编辑态） -->
                <template v-if="!isCreate">
                  <div class="rounded-2xl px-3.5 py-3"
                       :style="'background: var(--panel); border: 1px solid ' + urgency.border">
                    <div class="flex items-center gap-2">
                      <span class="text-xs font-semibold" style="color: var(--text-dim)">当前库存</span>
                      <span class="num text-2xl font-black" :style="'color:' + urgency.color">{{ localQty }}</span>
                      <span class="chip" :style="'color:' + urgency.color + '; border-color:' + urgency.border">
                        {{ urgency.text }}
                      </span>
                      <span class="ml-auto text-[11px]" style="color: var(--text-faint)">
                        阈值 {{ form.threshold }}
                      </span>
                    </div>
                    <div class="mt-2.5 flex items-center gap-2">
                      <button class="btn flex-1" :disabled="busy" @click="stock(-1)">
                        <Minus :size="15" /> 出库
                      </button>
                      <div class="w-28 flex-shrink-0">
                        <StepperInput v-model="amount" :min="1" :max="9999" :step="1" />
                      </div>
                      <button class="btn btn-primary flex-1" :disabled="busy" @click="stock(1)">
                        <Plus :size="15" /> 入库
                      </button>
                    </div>
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