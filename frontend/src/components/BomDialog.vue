<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  Dialog, DialogPanel, DialogTitle, TransitionChild, TransitionRoot,
} from '@headlessui/vue'
import {
  CheckCircle2, FileUp, ListPlus, PackageX, Play,
  ScanText, ShoppingCart, X,
} from '@lucide/vue'

import { api } from '../api/client'
import type { BomParseOut, BomPlan, BomStep } from '../api/types'
import { useBinsStore, type BinPosition } from '../stores/bins'
import NiceSelect, { type SelectOption } from './ui/NiceSelect.vue'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ close: []; start: [BomStep[]] }>()

const bins = useBinsStore()

// ---------- 状态 ----------
const text = ref('')
const fileName = ref('')
const parsed = ref<BomParseOut | null>(null)
const plan = ref<BomPlan | null>(null)
const busy = ref(false)
const errorMsg = ref<string | null>(null)
const view = ref<'work' | 'import'>('work')

interface RowEdit {
  key: number
  name: string
  value: string
  package: string
  manufacturerPart: string
  supplierPart: string
  quantity: number
  posKey: string        // 'z:l:s'，'' 表示未选
  status: 'pending' | 'ok' | 'err'
  err: string
}
const rows = ref<RowEdit[]>([])
const freeOptions = ref<BinPosition[]>([])
const doneCount = ref(0)

watch(
  () => props.open,
  (v) => {
    if (!v) return
    text.value = ''
    fileName.value = ''
    parsed.value = null
    plan.value = null
    errorMsg.value = null
    view.value = 'work'
    rows.value = []
    doneCount.value = 0
  },
)

// ---------- 工具 ----------
function errText(e: unknown): string {
  return e instanceof Error ? e.message : String(e)
}
function keyOf(p: BinPosition): string {
  return p.zone + ':' + p.layer + ':' + p.slot
}
function parseKey(k: string): BinPosition {
  const [zone, layer, slot] = k.split(':').map(Number)
  return { zone, layer, slot }
}

// ---------- 解析/规划 ----------
async function runParse() {
  if (!text.value.trim()) { errorMsg.value = '请先粘贴 BOM 文本或选择 xlsx 文件'; return }
  busy.value = true
  errorMsg.value = null
  try {
    parsed.value = await api.parseBom(text.value)
    plan.value = null
    view.value = 'work'
  } catch (e) { errorMsg.value = errText(e) } finally { busy.value = false }
}

async function onFile(ev: Event) {
  const input = ev.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  busy.value = true
  errorMsg.value = null
  try {
    if (/\.xlsx?$/i.test(file.name)) {
      parsed.value = await api.importBomFile(file)
    } else {
      // txt/csv：按文本读入同一解析通道
      text.value = await file.text()
      parsed.value = await api.parseBom(text.value)
    }
    fileName.value = file.name
    plan.value = null
    view.value = 'work'
  } catch (e) {
    errorMsg.value = errText(e)
    parsed.value = null
  } finally {
    busy.value = false
    input.value = ''
  }
}

async function runPlan() {
  busy.value = true
  errorMsg.value = null
  try {
    // 文件导入时 text 为空 → 由解析结果重建同构文本再规划
    const source = text.value.trim()
      ? text.value
      : (parsed.value?.lines ?? []).map((l) => l.raw).join('\n')
    if (!source.trim()) { errorMsg.value = '请先粘贴/导入 BOM'; return }
    plan.value = await api.planBom(source)
  } catch (e) { errorMsg.value = errText(e) } finally { busy.value = false }
}

// ---------- 整表入库（购买清单） ----------
function openImportList() {
  if (!parsed.value?.lines.length) { errorMsg.value = '请先解析/导入 BOM'; return }
  freeOptions.value = bins.freeSlots()
  rows.value = parsed.value.lines.map((l, i) => {
    const pos = freeOptions.value[i]
    return {
      key: i,
      name: l.name || l.value || '未命名',
      value: l.value ?? '',
      package: l.package ?? '',
      manufacturerPart: l.manufacturer_part ?? '',
      supplierPart: l.supplier_part ?? '',
      quantity: Math.max(1, l.quantity),
      posKey: pos ? keyOf(pos) : '',
      status: 'pending' as const,
      err: '',
    }
  })
  doneCount.value = 0
  view.value = 'import'
  const unplaced = rows.value.filter((r) => !r.posKey).length
  errorMsg.value = unplaced
    ? '空格不足：还有 ' + unplaced + ' 行没有默认位置，请手动选择或先在「设置」里扩容布局'
    : null
}

const slotOptions = computed<SelectOption[]>(() =>
  Array.from(slotLabels.value.entries()).map(([key, label]) => ({ value: key, label })),
)

const slotLabels = computed(() => {
  const map = new Map<string, string>()
  for (const p of freeOptions.value) map.set(keyOf(p), p.zone + '区/' + p.layer + '层/' + p.slot + '格')
  return map
})

async function importAll() {
  const pend = rows.value.filter((r) => r.status !== 'ok')
  if (!pend.length) return
  busy.value = true
  errorMsg.value = null
  doneCount.value = 0
  const taken = new Set<string>()
  let okRows = 0
  for (const row of pend) {
    if (!row.posKey || taken.has(row.posKey)) {
      row.status = 'err'
      row.err = row.posKey ? '该格已被本批次占用，请换一个' : '请选择放置格子'
      continue
    }
    const pos = parseKey(row.posKey)
    try {
      const created = await api.createComponent({
        name: row.name.trim() || '未命名',
        value: row.value.trim() || null,
        package: row.package.trim() || null,
        manufacturer_part: row.manufacturerPart.trim() || null,
        supplier_part: row.supplierPart.trim() || null,
        quantity: Math.max(1, row.quantity | 0),
        threshold: 5,
        zone: pos.zone, layer: pos.layer, slot: pos.slot,
      })
      bins.upsert(created)
      taken.add(row.posKey)
      row.status = 'ok'
      okRows++
    } catch (e) {
      row.status = 'err'
      row.err = errText(e)
    }
  }
  doneCount.value = okRows
  busy.value = false
  await bins.refreshAll()
}

const canStart = computed(() => !!plan.value && plan.value.steps.length > 0)
</script>

<template>
  <TransitionRoot :show="open" as="template">
    <Dialog as="div" class="relative z-50" @close="emit('close')">
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
            <DialogPanel class="glass-strong flex max-h-[90vh] w-full max-w-3xl flex-col rounded-2xl p-5">
              <div class="mb-3 flex items-center gap-2.5">
                <DialogTitle class="text-base font-extrabold tracking-wide">BOM 导入</DialogTitle>
                <button class="icon-btn ml-auto !h-8 !w-8" @click="emit('close')"><X :size="16" /></button>
              </div>

              <!-- ========== 工作区：粘贴文本 / xlsx 文件 ========== -->
              <div v-if="view === 'work'" class="flex flex-col gap-3">
                <div class="grid gap-2 sm:grid-cols-[1fr_auto]">
                  <textarea v-model="text" class="textarea mono !min-h-[96px] text-[12.5px]" spellcheck="false"
                            placeholder="粘贴 BOM 文本：每行一件，如 10k电阻 x20 / 100nF电容 0805 20个 / LED 5pcs；或直接选择下方的 .xlsx / .csv / .txt 文件" />
                  <div class="flex flex-col gap-2">
                    <label class="btn !justify-start border-dashed" :class="{ '!border-[var(--accent)]': busy }">
                      <FileUp :size="15" /> {{ busy ? '解析中…' : '选择 BOM 文件' }}
                      <input type="file" accept=".xlsx,.xls,.csv,.txt" class="hidden" @change="onFile" />
                    </label>
                    <span v-if="fileName" class="chip mono !text-[10.5px]" style="color: var(--accent)">
                      ✓ {{ fileName }}
                    </span>
                    <button class="btn" :disabled="busy" @click="runParse">
                      <ScanText :size="15" /> 解析预览
                    </button>
                  </div>
                </div>

                <div v-if="errorMsg" class="rounded-xl px-3 py-2 text-[12.5px] font-semibold"
                     style="background: rgba(255,92,122,.12); color: var(--danger)">{{ errorMsg }}</div>

                <div class="flex flex-wrap items-center gap-2">
                  <span v-if="parsed" class="chip">
                    {{ parsed.lines.length }} 行 · {{ parsed.total_quantity }} 件
                    <span v-if="fileName" class="mono">（{{ fileName }}）</span>
                  </span>
                  <div class="flex-1" />
                  <button class="btn" :disabled="!parsed || busy" @click="runPlan">
                    <Play :size="15" /> 匹配库存并规划
                  </button>
                  <button class="btn btn-primary" :disabled="!parsed || busy" @click="openImportList">
                    <ListPlus :size="15" /> 整表入库
                  </button>
                </div>

                <!-- 预览表 -->
                <div v-if="parsed" class="fade-up max-h-44 overflow-y-auto rounded-xl"
                     style="border: 1px solid var(--line-strong)">
                  <table class="w-full text-left text-[12.5px]">
                    <thead class="sticky top-0 z-10" style="background: var(--surface-2)">
                      <tr>
                        <th class="px-3 py-1.5 term-label !text-[9px]">元件/原文</th>
                        <th class="px-2 py-1.5 term-label !text-[9px]">值</th>
                        <th class="px-2 py-1.5 term-label !text-[9px]">封装</th>
                        <th class="px-3 py-1.5 text-right term-label !text-[9px]">数量</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="(line, i) in parsed.lines" :key="i"
                          :style="i % 2 ? 'background: rgba(255,255,255,.02)' : ''">
                        <td class="max-w-[300px] px-3 py-1.5">
                          <span class="font-bold">{{ line.name || line.raw }}</span>
                          <span v-if="line.raw !== line.name" class="ml-2 text-[11px]" style="color: var(--text-faint)">
                            {{ line.raw }}
                          </span>
                        </td>
                        <td class="px-2 py-1.5 mono">{{ line.value || '—' }}</td>
                        <td class="px-2 py-1.5 mono">{{ line.package || '—' }}</td>
                        <td class="num px-3 py-1.5 text-right font-bold">×{{ line.quantity }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>

                <!-- 规划结果 -->
                <template v-if="plan">
                  <div v-if="plan.missing.length" class="fade-up rounded-xl px-4 py-3"
                       style="border:1px solid rgba(217,178,62,.5); background: rgba(217,178,62,.08)">
                    <div class="mb-2 flex items-center gap-2 text-[13px] font-extrabold" style="color: var(--warn)">
                      <PackageX :size="15" /> 库存不足，请先补货（{{ plan.missing.length }} 项）
                    </div>
                    <div class="overflow-hidden rounded-lg" style="border: 1px solid var(--line)">
                      <div class="grid grid-cols-[64px_1fr_72px_72px] gap-2 px-2.5 py-1 text-[10.5px] font-bold"
                           style="color: var(--text-faint); background: rgba(255,255,255,.03)">
                        <span>状态</span><span>物料</span>
                        <span class="text-right">还差</span>
                        <span class="text-right">现有</span>
                      </div>
                      <div v-for="(m, i) in plan.missing" :key="i"
                           class="grid grid-cols-[64px_1fr_72px_72px] items-center gap-2 px-2.5 py-1.5 text-[12.5px]"
                           :style="i ? 'border-top: 1px solid var(--line)' : ''">
                        <span class="chip !px-1.5 !text-[10px]"
                              :style="m.reason === 'shortage' ? 'color: var(--danger)' : 'color: var(--info)'">
                          {{ m.reason === 'shortage' ? '量不足' : '无库存' }}
                        </span>
                        <span class="truncate font-bold">
                          {{ m.name || m.raw }}
                          <span v-if="m.value" class="ml-1.5 font-normal" style="color: var(--text-dim)">{{ m.value }}</span>
                          <span v-if="m.package" class="ml-1.5 font-normal" style="color: var(--text-faint)">{{ m.package }}</span>
                        </span>
                        <span class="num text-right font-bold" style="color: var(--warn)">{{ m.quantity }}</span>
                        <span class="num text-right" style="color: var(--text-dim)">
                          {{ m.available !== null ? m.available : '—' }}
                        </span>
                      </div>
                    </div>
                  </div>
                  <div class="fade-up flex flex-col gap-1.5 rounded-xl px-4 py-3"
                       style="border: 1px solid var(--line-strong); background: var(--panel)">
                    <div class="text-[12.5px] font-extrabold" style="color: var(--accent-ink)">取料顺序（共 {{ plan.steps.length }} 步）</div>
                    <div v-for="(step, i) in plan.steps" :key="step.component.id"
                         class="flex items-center gap-2 rounded-lg px-2 py-1.5 text-[12.5px]"
                         :style="i ? 'border-top: 1px solid var(--line)' : ''">
                      <span class="chip num !text-[10px]" style="color: var(--accent)">
                        {{ String(i + 1).padStart(2, '0') }}
                      </span>
                      <span class="font-bold">{{ step.component.name }}</span>
                      <span v-if="step.component.value" class="mono" style="color: var(--text-dim)">{{ step.component.value }}</span>
                      <span v-if="step.component.package" class="mono" style="color: var(--text-faint)">{{ step.component.package }}</span>
                      <span class="ml-auto num font-bold" style="color: var(--accent-ink)">取 ×{{ step.quantity }}</span>
                      <span v-if="step.component.led_index !== null" class="chip mono !text-[9.5px]">LED {{ step.component.led_index }}</span>
                    </div>
                  </div>
                </template>

                <div v-if="plan" class="mt-1 flex items-center gap-2">
                  <span class="text-[11px]" style="color: var(--text-faint)">引导时每步自动出库并记入操作流水</span>
                  <div class="flex-1" />
                  <button class="btn btn-ghost" @click="emit('close')">关闭</button>
                  <button class="btn btn-primary" :disabled="!canStart" @click="plan && emit('start', plan.steps)">
                    <ShoppingCart :size="15" /> 开始引导
                  </button>
                </div>
              </div>

              <!-- ========== 整表入库（购买清单）：逐项选格 ========== -->
              <div v-else class="flex min-h-0 flex-col gap-3">
                <div class="flex items-center gap-2">
                  <span class="text-sm font-extrabold">整表入库</span>
                  <span v-if="fileName" class="chip mono !text-[10px]" style="color: var(--accent)">{{ fileName }}</span>
                  <span class="chip mono !text-[10px]">{{ rows.length }} 项</span>
                  <button class="btn btn-ghost ml-auto !py-1 text-xs" @click="view = 'work'">返回</button>
                </div>

                <div v-if="errorMsg" class="rounded-xl px-3 py-2 text-[12.5px] font-semibold"
                     style="background: rgba(255,92,122,.12); color: var(--danger)">{{ errorMsg }}</div>

                <div v-if="doneCount > 0" class="rounded-xl px-3 py-2 text-[12.5px] font-bold"
                     style="background: rgba(103,185,140,.12); color: var(--success)">
                  <CheckCircle2 :size="14" class="mr-1 inline" /> {{ doneCount }} 项已入库，可继续处理其余行
                </div>

                <div class="min-h-0 flex-1 space-y-1.5 overflow-y-auto pr-1">
                  <div v-for="row in rows" :key="row.key"
                       class="grid grid-cols-[minmax(0,1fr)_96px_84px_64px_150px_20px] items-center gap-2 rounded-lg px-2 py-1.5 text-[12.5px]"
                       :style="row.status === 'err' ? 'background: rgba(255,92,122,.08)'
                         : row.status === 'ok' ? 'background: rgba(103,185,140,.06)'
                         : 'background: rgba(255,255,255,.025)'">
                    <input v-model="row.name" class="input !px-2 !py-1 text-[12.5px]" :disabled="row.status === 'ok'" />
                    <input v-model="row.value" class="input mono !px-2 !py-1 text-[12px]" placeholder="值" :disabled="row.status === 'ok'" />
                    <input v-model="row.package" class="input mono !px-2 !py-1 text-[12px]" placeholder="封装" :disabled="row.status === 'ok'" />
                    <input v-model.number="row.quantity" type="number" min="1" class="input num !px-2 !py-1 text-[12px]" :disabled="row.status === 'ok'" />
                    <NiceSelect v-model="row.posKey" :options="slotOptions"
                                :disabled="row.status === 'ok'" placeholder="空格位…" />
                    <span v-if="row.status === 'ok'" class="mono text-[11px] font-bold text-center" style="color: var(--success)">✓</span>
                    <span v-else-if="row.status === 'err'" class="mono text-[11px] font-bold text-center" :title="row.err" style="color: var(--danger)">✗</span>
                    <span v-else class="mono text-[10px] text-center" style="color: var(--text-faint)">…</span>
                    <div v-if="row.manufacturerPart || row.supplierPart"
                         class="mono col-span-full -mt-0.5 truncate px-1 text-[9.5px]"
                         style="color: var(--text-faint)">
                      <span style="color: var(--text-dim)">厂商料号</span> {{ row.manufacturerPart || '—' }}
                      <span class="mx-1" style="color: var(--line-strong)">|</span>
                      <span style="color: var(--text-dim)">供应商料号</span> {{ row.supplierPart || '—' }}
                    </div>
                  </div>
                </div>

                <div class="flex items-center gap-2">
                  <span class="text-[11px]" style="color: var(--text-faint)">
                    每行独立选格（默认顺序填空位）；数量按 BOM 原值建档，阈值默认 5
                  </span>
                  <div class="flex-1" />
                  <button class="btn btn-ghost" @click="emit('close')">关闭</button>
                  <button class="btn btn-primary" :disabled="busy" @click="importAll">
                    <ListPlus :size="15" /> 全部入库
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