<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  Dialog, DialogPanel, DialogTitle, TransitionChild, TransitionRoot,
} from '@headlessui/vue'
import { CheckCircle2, ListPlus, PackagePlus, Plus, Trash2, X } from '@lucide/vue'

import { api } from '../api/client'
import type { BinPosition } from '../stores/bins'
import { useBinsStore } from '../stores/bins'
import NiceSelect, { type SelectOption } from './ui/NiceSelect.vue'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ close: [] }>()

const bins = useBinsStore()

interface Row {
  key: number
  name: string
  value: string
  package: string
  manufacturerPart: string
  supplierPart: string
  tagsText: string
  quantity: number
  posKey: string
  status: 'pending' | 'ok' | 'err'
  err: string
}

const rows = ref<Row[]>([])
const freeOptions = ref<BinPosition[]>([])
const busy = ref(false)
const errorMsg = ref<string | null>(null)
const okCount = ref(0)
let seq = 0

const slotOptions = computed<SelectOption[]>(() =>
  freeOptions.value.map((p) => ({
    value: keyOf(p),
    label: `${p.zone}区/${p.layer}层/${p.slot}格`,
  })),
)

function keyOf(p: BinPosition): string {
  return `${p.zone}:${p.layer}:${p.slot}`
}

function parsePos(k: string): BinPosition {
  const [zone, layer, slot] = k.split(':').map(Number)
  return { zone, layer, slot }
}

function parseTags(text: string): string[] {
  const seen: string[] = []
  for (const raw of text.split(/[,，、\s]+/)) {
    const item = raw.trim().slice(0, 20)
    if (item && !seen.includes(item) && seen.length < 8) seen.push(item)
  }
  return seen
}

function newRow(force = false): Row | null {
  if (!force && rows.value.length >= 1 && rows.value[rows.value.length - 1].status === 'pending'
      && !rows.value[rows.value.length - 1].name.trim()) {
    return null
  }
  const pos = freeOptions.value[rows.value.length]
  return {
    key: ++seq,
    name: '',
    value: '',
    package: '',
    manufacturerPart: '',
    supplierPart: '',
    tagsText: '',
    quantity: 1,
    posKey: pos ? keyOf(pos) : '',
    status: 'pending',
    err: '',
  }
}

function refreshFree() {
  freeOptions.value = bins.freeSlots()
}

function setupRows() {
  refreshFree()
  rows.value = []
  okCount.value = 0
  errorMsg.value = null
  const first = newRow(true)
  if (first) rows.value = [first]
}

async function importAll() {
  const pend = rows.value.filter((r) => r.status !== 'ok')
  if (!pend.length) return
  busy.value = true
  errorMsg.value = null
  okCount.value = 0
  const taken = new Set<string>()
  let done = 0
  for (const row of pend) {
    if (!row.posKey || taken.has(row.posKey)) {
      row.status = 'err'
      row.err = row.posKey ? '该格已被本批占用' : '请选择放置格子'
      continue
    }
    try {
      const created = await api.createComponent({
        name: row.name.trim() || '未命名',
        value: row.value.trim() || null,
        package: row.package.trim() || null,
        manufacturer_part: row.manufacturerPart.trim() || null,
        supplier_part: row.supplierPart.trim() || null,
        tags: parseTags(row.tagsText),
        quantity: Math.max(1, row.quantity | 0),
        threshold: 5,
        zone: parsePos(row.posKey).zone,
        layer: parsePos(row.posKey).layer,
        slot: parsePos(row.posKey).slot,
      })
      bins.upsert(created)
      taken.add(row.posKey)
      row.status = 'ok'
      done++
    } catch (e) {
      row.status = 'err'
      row.err = e instanceof Error ? e.message : String(e)
    }
  }
  okCount.value = done
  busy.value = false
  await bins.refreshAll()
  refreshFree()
}

function close() {
  emit('close')
}

function addRow() {
  const row = newRow()
  if (row) rows.value.push(row)
}

watch(() => props.open, (v) => { if (v) setupRows() })
</script>

<template>
  <TransitionRoot :show="open" as="template">
    <Dialog as="div" class="relative z-50" @close="close">
      <TransitionChild as="template" enter="duration-200 ease-out" enter-from="opacity-0"
                       leave="duration-150 ease-in" leave-to="opacity-0">
        <div class="fixed inset-0 bg-black/60 backdrop-blur-[6px]" />
      </TransitionChild>
      <div class="fixed inset-0 overflow-y-auto">
        <div class="flex min-h-full items-center justify-center p-4">
          <TransitionChild as="template" enter="duration-200 ease-out"
                           enter-from="opacity-0 translate-y-3 scale-95"
                           enter-to="opacity-100 translate-y-0 scale-100"
                           leave="duration-150 ease-in" leave-to="opacity-0 translate-y-3 scale-95">
            <DialogPanel class="glass-strong flex max-h-[90vh] w-full max-w-4xl flex-col rounded-2xl p-5">
              <div class="mb-3 flex items-center gap-2.5">
                <PackagePlus :size="17" style="color: var(--accent)" />
                <DialogTitle class="text-base font-extrabold">手工入库</DialogTitle>
                <button class="icon-btn ml-auto !h-8 !w-8" @click="close"><X :size="16" /></button>
              </div>

              <div v-if="errorMsg" class="mb-2 rounded-xl px-3 py-2 text-[12.5px] font-semibold"
                   style="background: rgba(255,92,122,.12); color: var(--danger)">{{ errorMsg }}</div>
              <div v-if="okCount > 0" class="mb-2 rounded-xl px-3 py-2 text-[12.5px] font-bold"
                   style="background: rgba(103,185,140,.12); color: var(--success)">
                <CheckCircle2 :size="14" class="mr-1 inline" />{{ okCount }} 项已入库
              </div>

              <div class="flex flex-col gap-3">
                <!-- 表头提示列（紧凑网格） -->
                <div class="grid grid-cols-[minmax(150px,1.4fr)_88px_76px_1.1fr_92px_64px_1fr_150px_28px] gap-2 px-1 text-[10px] font-bold"
                     style="color: var(--text-faint)">
                  <span>名称</span><span>值</span><span>封装</span><span>厂商料号</span>
                  <span>供应商料号</span><span class="text-right">数量</span><span>格子标签</span>
                  <span>放置位置</span><span />
                </div>
                <div class="max-h-[52vh] space-y-1.5 overflow-y-auto pr-1">
                  <div v-for="row in rows" :key="row.key"
                       class="rounded-lg px-1.5 py-1.5"
                       :style="row.status === 'err' ? 'background: rgba(255,92,122,.08)'
                         : row.status === 'ok' ? 'background: rgba(103,185,140,.06)'
                         : 'background: rgba(255,255,255,.025)'">
                    <div class="grid grid-cols-[minmax(150px,1.4fr)_88px_76px_1.1fr_92px_64px_1fr_150px_28px] items-center gap-2">
                      <input v-model="row.name" class="input !px-2 !py-1 text-[12.5px]" placeholder="必填" :disabled="row.status === 'ok'" />
                      <input v-model="row.value" class="input mono !px-2 !py-1 text-[12px]" :disabled="row.status === 'ok'" />
                      <input v-model="row.package" class="input mono !px-2 !py-1 text-[12px]" :disabled="row.status === 'ok'" />
                      <input v-model="row.manufacturerPart" class="input mono !px-2 !py-1 text-[12px]" :disabled="row.status === 'ok'" />
                      <input v-model="row.supplierPart" class="input mono !px-2 !py-1 text-[12px]" :disabled="row.status === 'ok'" />
                      <input v-model.number="row.quantity" type="number" min="1"
                             class="input num !px-2 !py-1 text-[12px] text-center" :disabled="row.status === 'ok'" />
                      <input v-model="row.tagsText" class="input mono !px-2 !py-1 text-[12px]" :disabled="row.status === 'ok'" />
                      <NiceSelect v-model="row.posKey" :options="slotOptions"
                                  :disabled="row.status === 'ok'" placeholder="空格位…" />
                      <button class="icon-btn !h-7 !w-7 !rounded-lg" :disabled="row.status === 'ok'"
                              :title="row.err || '删除该行'" @click="rows = rows.filter(x => x.key !== row.key)">
                        <Trash2 :size="13" />
                      </button>
                    </div>
                    <div v-if="row.status === 'err'" class="mt-1 px-1 text-[11px] font-semibold" style="color: var(--danger)">
                      {{ row.err }}
                    </div>
                  </div>
                </div>
              </div>

              <div class="mt-3 flex items-center gap-2">
                <button class="btn" @click="addRow">
                  <Plus :size="14" /> 加一行
                </button>
                <div class="flex-1" />
                <button class="btn btn-ghost" @click="close">关闭</button>
                <button class="btn btn-primary" :disabled="busy" @click="importAll">
                  <ListPlus :size="15" /> 全部入库
                </button>
              </div>
            </DialogPanel>
          </TransitionChild>
        </div>
      </div>
    </Dialog>
  </TransitionRoot>
</template>