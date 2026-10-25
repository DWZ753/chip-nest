<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import {
  Dialog, DialogPanel, DialogTitle, TransitionChild, TransitionRoot,
} from '@headlessui/vue'
import {
  CheckCircle2, Crosshair, FileUp, ListPlus, PackageX, Play,
  ScanSearch, ScanText, ShoppingCart, X,
} from '@lucide/vue'

import { api } from '../api/client'
import type { BomParseOut, BomPlan, BomStep, BomProject } from '../api/types'
import { useBinsStore, type BinPosition } from '../stores/bins'
import { usePickerStore } from '../stores/picker'
import { suggestThreshold } from '../utils/stock'
import InventoryMaintenancePanel from './inventory_maintenance_panel.vue'
import OperationHistoryPanel from './operation_history_panel.vue'
import MotionTabs from './ui/motion_tabs.vue'
import MotionPanel from './ui/motion_panel.vue'
import StocktakePanel from './stocktake_panel.vue'
import ReplenishmentPanel from './replenishment_panel.vue'
import BomProjectPanel from './bom_project_panel.vue'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{
  close: []; manual: []; start: [BomStep[], BomProject?]; afterLeave: []
}>()

const bins = useBinsStore()

// ---------- 状态 ----------
const text = ref('')
const fileName = ref('')
const parsed = ref<BomParseOut | null>(null)
const plan = ref<BomPlan | null>(null)
const selections = ref<Record<number, number>>({})
const busy = ref(false)
const errorMsg = ref<string | null>(null)
const view = ref<'work' | 'import'>('work')
const active_tab = ref('intake')
const project_panel = ref<InstanceType<typeof BomProjectPanel> | null>(null)
const current_project = ref<BomProject | null>(null)
const copies = ref(1)
const project_busy = ref(false)
const tabs = [
  { key: 'intake', label: '入库' },
  { key: 'pick', label: 'BOM 取料' },
  { key: 'maintenance', label: '元件整理' },
  { key: 'stocktake', label: '盘点' },
  { key: 'replenishment', label: '补货清单' },
  { key: 'history', label: '操作记录' },
]

function switch_tab(key: string) {
  active_tab.value = key
  view.value = 'work'
}

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

watch(text, () => {
  parsed.value = null
  plan.value = null
  selections.value = {}
  fileName.value = ''
})

watch(
  () => props.open,
  (v) => {
    if (!v) return
    active_tab.value = 'intake'
    text.value = ''
    fileName.value = ''
    parsed.value = null
    plan.value = null
    errorMsg.value = null
    view.value = 'work'
    rows.value = []
    doneCount.value = 0
    idBusy.value = false
    idStop.value = false
    idDone.value = 0
    idTotal.value = 0
    current_project.value = null
    copies.value = 1
    project_busy.value = false
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
  if (!text.value.trim()) { errorMsg.value = '没有 BOM 内容'; return }
  busy.value = true
  errorMsg.value = null
  parsed.value = null
  plan.value = null
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
  text.value = ''
  parsed.value = null
  plan.value = null
  fileName.value = ''
  busy.value = true
  errorMsg.value = null
  try {
    if (/\.(xlsx|csv)$/i.test(file.name)) {
      parsed.value = await api.importBomFile(file)
    } else {
      // txt：按文本读入同一解析通道
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
  await updatePlan()
}

/** 重开项目时先完成文本重置，避免异步 watch 清掉保存的匹配。 */
async function load_project(project: BomProject) {
  text.value = ''
  await nextTick()
  fileName.value = project.name
  parsed.value = { lines: project.lines,
    total_quantity: project.lines.reduce((total, line) => total + line.quantity, 0) }
  selections.value = { ...project.selections }
  plan.value = project.plan
  errorMsg.value = null
}

/** 新项目清空取料工作区，已经保存的记录继续保留。 */
function reset_project() {
  text.value = ''
  fileName.value = ''
  parsed.value = null
  plan.value = null
  selections.value = {}
  current_project.value = null
}

/** 修改份数后重新规划，防止使用上一份数的取料数量。 */
function set_copies(value: number) {
  copies.value = value
  plan.value = null
}

/** 引导前保存最新规划，后续步骤与持久化项目绑定。 */
async function start_project() {
  const project = await project_panel.value?.prepare_start()
  if (!project) return
  if (project.plan.choices.length) {
    errorMsg.value = '匹配未完成'
    return
  }
  const remaining = project.plan.steps.slice(project.cursor).map(step => ({
    ...step, component: bins.components.find(comp => comp.id === step.component.id)
      ?? step.component,
  }))
  if (remaining.length) emit('start', remaining, project)
}

async function chooseCandidate(line_index: number, component_id: number) {
  if (busy.value) return
  const previous = selections.value[line_index]
  selections.value[line_index] = component_id
  if (!await updatePlan()) {
    if (previous === undefined) delete selections.value[line_index]
    else selections.value[line_index] = previous
  }
}

async function updatePlan(): Promise<boolean> {
  busy.value = true
  errorMsg.value = null
  try {
    if (parsed.value?.lines.length) {
      if (!Number.isInteger(copies.value) || copies.value < 1 || copies.value > 10000) {
        errorMsg.value = '制作份数无效'
        return false
      }
      if (current_project.value?.cursor) {
        return !!await project_panel.value?.prepare_start()
      }
      plan.value = await api.planBomRows(parsed.value.lines.map(line => ({
        ...line, quantity: line.quantity * (active_tab.value === 'pick' ? copies.value : 1),
      })), selections.value)
      return true
    } else {
      errorMsg.value = '没有 BOM 内容'
    }
  } catch (e) { errorMsg.value = errText(e) } finally { busy.value = false }
  return false
}

// ---------- 整表入库（购买清单） ----------
function openImportList() {
  if (!parsed.value?.lines.length) { errorMsg.value = '没有解析结果'; return }
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
    ? '空格不足：还有 ' + unplaced + ' 行没有默认位置'
    : null
}

// 选格：回主页面点一个空格，填给这一行
const picker = usePickerStore()

function slotLabel(key: string): string {
  const [z, l, s] = key.split(':')
  return `${z}区/${l}层/${s}格`
}

async function pickSlot(row: RowEdit) {
  const pos = await picker.request()
  if (!pos) return
  const key = keyOf(pos)
  if (rows.value.some((r) => r !== row && r.status !== 'ok' && r.posKey === key)) {
    row.err = '该格已被本批次占用'
    row.status = 'err'
    return
  }
  row.posKey = key
  row.err = ''
  if (row.status === 'err') row.status = 'pending'
}

// ---------- 联网识别料号（整表入库用） ----------
const idBusy = ref(false)
const idDone = ref(0)
const idTotal = ref(0)
const idStop = ref(false)

function rowQuery(row: RowEdit): string {
  const code = (row.supplierPart || row.manufacturerPart || '').trim()
  if (code) return code
  const byValue = [row.value, row.package].map((s) => (s || '').trim()).filter(Boolean)
  if (byValue.length) return byValue.join(' ')
  return [row.name, row.package].map((s) => (s || '').trim()).filter(Boolean).join(' ')
}

async function identifyRow(row: RowEdit): Promise<boolean> {
  const query = rowQuery(row)
  if (!query) { row.err = '没有可识别的信息'; return false }
  const res = await api.lookupAutofill(query)
  const best = res.best
  if (!best) { row.err = '没查到对应元件'; return false }
  if (!row.name.trim() || row.name === '未命名') row.name = best.name || row.name
  if (!row.value.trim() && best.value) row.value = best.value
  if (!row.package.trim() && best.package) row.package = best.package
  if (!row.manufacturerPart.trim() && best.mpn) row.manufacturerPart = best.mpn
  if (!row.supplierPart.trim() && best.lcsc) row.supplierPart = best.lcsc
  row.err = ''
  return true
}

async function identifyAll() {
  if (idBusy.value) return
  const targets = rows.value.filter((r) => r.status !== 'ok' && !r.supplierPart.trim())
  if (!targets.length) return
  idBusy.value = true
  idStop.value = false
  idDone.value = 0
  idTotal.value = targets.length
  errorMsg.value = null
  for (const row of targets) {
    if (idStop.value) break
    try {
      await identifyRow(row)
    } catch (e) {
      row.err = errText(e)
    }
    idDone.value += 1
  }
  idBusy.value = false
}

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
      row.err = row.posKey ? '该格已被本批次占用' : '未选择格子'
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
        threshold: suggestThreshold(Math.max(1, row.quantity | 0)),
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

const canStart = computed(() => !busy.value && !!plan.value
  && plan.value.steps.length > 0 && plan.value.choices.length === 0)
</script>

<template>
  <TransitionRoot :show="open && !picker.active" as="template"
                  @after-leave="emit('afterLeave')">
    <Dialog as="div" class="relative z-50" @close="emit('close')">
      <TransitionChild as="template" enter="dialog-backdrop-enter"
                       enter-from="opacity-0" enter-to="opacity-100"
                       leave="dialog-backdrop-leave" leave-to="opacity-0">
        <div class="fixed inset-0 bg-black/60 backdrop-blur-[6px]" />
      </TransitionChild>

      <div class="fixed inset-0 overflow-y-auto">
        <div class="flex min-h-full items-center justify-center p-4">
          <TransitionChild as="template"
                           leave="dialog-panel-leave"
                           leave-to="dialog-panel-to">
            <DialogPanel class="motion-dialog glass-strong flex max-h-[90vh]
              w-full max-w-3xl flex-col rounded-2xl p-5">
              <div class="mb-3 flex items-center gap-2.5">
                <DialogTitle class="text-base font-extrabold tracking-wide">库存</DialogTitle>
                <button v-if="active_tab === 'intake'"
                        class="btn ml-auto !px-3 !py-1.5 text-xs"
                        @click="emit('manual')">
                  <ListPlus :size="14" /> 手工入库
                </button>
                <button class="icon-btn !h-8 !w-8"
                        :class="active_tab === 'intake' ? '' : 'ml-auto'"
                        @click="emit('close')"><X :size="16" /></button>
              </div>

              <MotionTabs :model-value="active_tab" :tabs="tabs"
                          label="库存分组" :disabled="busy || idBusy || project_busy"
                          @update:model-value="switch_tab" />
              <MotionPanel :active_key="active_tab + ':' + view"
                           :page_order="tabs.flatMap(tab =>
                             [tab.key + ':work', tab.key + ':import'])">
              <template #default="{ page_key }">
              <div class="flex min-h-0 flex-1 flex-col">
              <InventoryMaintenancePanel
                v-if="page_key === 'maintenance:work'" />
              <OperationHistoryPanel
                :active="page_key === active_tab + ':' + view"
                v-else-if="page_key === 'history:work'" />
              <StocktakePanel v-else-if="page_key === 'stocktake:work'" />
              <ReplenishmentPanel
                :active="page_key === active_tab + ':' + view"
                v-else-if="page_key === 'replenishment:work'" />
              <!-- ========== 工作区：粘贴文本 / xlsx 文件 ========== -->
              <div v-else-if="page_key.endsWith(':work')"
                   class="flex min-h-0 flex-1 flex-col gap-3
                     overflow-y-auto pr-1">
                <BomProjectPanel v-if="page_key.startsWith('pick:')"
                  ref="project_panel"
                  :lines="parsed?.lines ?? null" :selections="selections"
                  :file-name="fileName" :disabled="busy || idBusy"
                  @load="load_project" @reset="reset_project" @copies="set_copies"
                  @project="current_project = $event" @plan="plan = $event"
                  @busy="project_busy = $event" />
                <h3 class="text-[13px] font-extrabold">
                  {{ page_key.startsWith('intake:')
                    ? 'BOM 入库' : 'BOM 取料' }}
                </h3>
                <div class="grid gap-2 sm:grid-cols-[1fr_auto]">
                  <textarea v-model="text" class="textarea mono !min-h-[96px] text-[12.5px]" spellcheck="false"
                            :disabled="project_busy
                              || (page_key.startsWith('pick:')
                              && !!current_project?.cursor)"
                            placeholder="BOM 内容" />
                  <div class="flex flex-col gap-2">
                    <label class="btn !justify-start border-dashed" :class="{ '!border-[var(--accent)]': busy }">
                      <FileUp :size="15" /> {{ busy ? '解析中…' : '选择 BOM 文件' }}
                      <input type="file" accept=".xlsx,.csv,.txt" class="hidden"
                        :disabled="busy || project_busy
                          || (page_key.startsWith('pick:')
                            && !!current_project?.cursor)"
                        @change="onFile" />
                    </label>
                    <span v-if="fileName" class="chip mono !text-[10.5px]" style="color: var(--accent)">
                      ✓ {{ fileName }}
                    </span>
                    <button class="btn" :disabled="busy || project_busy
                          || (page_key.startsWith('pick:')
                            && !!current_project?.cursor)" @click="runParse">
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
                  <button v-if="page_key.startsWith('pick:')" class="btn"
                          :disabled="!parsed || busy || project_busy" @click="runPlan">
                    <Play :size="15" /> 匹配库存并规划
                  </button>
                  <button v-else class="btn btn-primary"
                          :disabled="!parsed || busy" @click="openImportList">
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
                <template v-if="plan && page_key.startsWith('pick:')">
                  <div v-if="plan.choices.length" class="fade-up rounded-xl px-4 py-3"
                       style="border: 1px solid var(--line-strong); background: var(--panel)">
                    <div class="mb-2 text-[13px] font-extrabold" style="color: var(--warn)">
                      待确认（{{ plan.choices.length }} 项）
                    </div>
                    <div v-for="choice in plan.choices" :key="choice.line_index"
                         class="mb-3 last:mb-0">
                      <div class="mb-1.5 flex flex-wrap items-center gap-2 text-[12.5px]">
                        <span class="chip">第 {{ choice.line_index + 1 }} 行</span>
                        <span class="font-bold">{{ choice.line.name || choice.line.raw }}</span>
                        <span class="mono">{{ choice.line.value }} {{ choice.line.package }}</span>
                        <span class="num">×{{ choice.line.quantity }}</span>
                      </div>
                      <div v-if="choice.line.manufacturer_part || choice.line.supplier_part"
                           class="mb-1.5 break-all text-[11px]" style="color: var(--text-dim)">
                        厂商料号 {{ choice.line.manufacturer_part || '—' }} ·
                        供应商料号 {{ choice.line.supplier_part || '—' }}
                      </div>
                      <div class="flex flex-col gap-1.5">
                        <button v-for="candidate in choice.candidates" :key="candidate.component.id"
                                class="btn !justify-start !whitespace-normal text-left"
                                :disabled="busy"
                                @click="chooseCandidate(choice.line_index, candidate.component.id)">
                          <div class="min-w-0 flex-1">
                            <div class="flex flex-wrap items-center gap-2 text-[12px]">
                              <span class="font-bold">{{ candidate.component.name }}</span>
                              <span class="mono">{{ candidate.component.value }} {{ candidate.component.package }}</span>
                              <span class="num">库存 {{ candidate.component.quantity }}</span>
                              <span>{{ candidate.component.zone }}区 / {{ candidate.component.layer }}层 / {{ candidate.component.slot }}格</span>
                            </div>
                            <div v-if="candidate.component.manufacturer_part || candidate.component.supplier_part"
                                 class="mt-1 break-all text-[11px]" style="color: var(--text-dim)">
                              厂商料号 {{ candidate.component.manufacturer_part || '—' }} ·
                              供应商料号 {{ candidate.component.supplier_part || '—' }}
                            </div>
                            <div class="mt-1 flex flex-wrap gap-1">
                              <span v-for="reason in candidate.reasons" :key="reason"
                                    class="chip !text-[10px]"
                                    :style="reason.includes('不一致') ? 'color: var(--danger)' : 'color: var(--text-dim)'">
                                {{ reason }}
                              </span>
                            </div>
                          </div>
                          <span class="shrink-0 text-[12px]">选择</span>
                        </button>
                      </div>
                    </div>
                  </div>
                  <div v-if="plan.missing.length" class="fade-up rounded-xl px-4 py-3"
                       style="border:1px solid rgba(217,178,62,.5); background: var(--panel-strong)">
                    <div class="mb-2 flex items-center gap-2 text-[13px] font-extrabold" style="color: var(--warn)">
                      <PackageX :size="15" /> 库存不足（{{ plan.missing.length }} 项）
                    </div>
                    <div class="overflow-hidden rounded-lg"
                         style="border: 1px solid var(--line); background: var(--surface)">
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
                    <div class="text-[12.5px] font-extrabold" style="color: var(--accent-ink)">取料顺序 · {{ plan.steps.length }} 步</div>
                    <div v-for="(step, i) in plan.steps" :key="step.component.id"
                         class="flex items-center gap-2 rounded-lg px-2 py-1.5 text-[12.5px]"
                         :style="i ? 'border-top: 1px solid var(--line)' : ''">
                      <span class="chip num !text-[10px]" style="color: var(--accent)">
                        {{ String(i + 1).padStart(2, '0') }}
                      </span>
                      <span class="font-bold">{{ step.component.name }}</span>
                      <span v-if="step.component.value" class="mono" style="color: var(--text-dim)">{{ step.component.value }}</span>
                      <span v-if="step.component.package" class="mono" style="color: var(--text-faint)">{{ step.component.package }}</span>
                      <span v-if="i < (current_project?.cursor ?? 0)" class="chip">已取</span>
                      <span class="ml-auto num font-bold" style="color: var(--accent-ink)">取 ×{{ step.quantity }}</span>
                      <span v-if="step.component.led_index !== null" class="chip mono !text-[9.5px]">LED {{ step.component.led_index }}</span>
                    </div>
                  </div>
                </template>

                <div v-if="plan && page_key.startsWith('pick:')"
                     class="mt-1 flex items-center gap-2">
                  <div class="flex-1" />
                  <button class="btn btn-ghost" @click="emit('close')">关闭</button>
                  <button class="btn btn-primary" :disabled="!canStart || project_busy
                    || (current_project?.cursor ?? 0) >= plan.steps.length"
                    @click="start_project">
                    <ShoppingCart :size="15" /> {{ current_project?.cursor ? '继续取料' : '开始引导' }}
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
                       class="grid grid-cols-[minmax(0,1fr)_96px_84px_64px_150px_20px_22px] items-center gap-2 rounded-lg px-2 py-1.5 text-[12.5px]"
                       :style="row.status === 'err' ? 'background: rgba(255,92,122,.08)'
                         : row.status === 'ok' ? 'background: rgba(103,185,140,.06)'
                         : 'background: rgba(255,255,255,.025)'">
                    <input v-model="row.name" class="input !px-2 !py-1 text-[12.5px]" :disabled="row.status === 'ok'" />
                    <input v-model="row.value" class="input mono !px-2 !py-1 text-[12px]" placeholder="值" :disabled="row.status === 'ok'" />
                    <input v-model="row.package" class="input mono !px-2 !py-1 text-[12px]" placeholder="封装" :disabled="row.status === 'ok'" />
                    <input v-model.number="row.quantity" type="number" min="1" class="input num !px-2 !py-1 text-[12px]" :disabled="row.status === 'ok'" />
                    <button class="btn w-full !px-2 !py-1 text-[11.5px]"
                            :disabled="row.status === 'ok'" @click="pickSlot(row)">
                      <Crosshair :size="12" class="mr-1 inline" />
                      {{ row.posKey ? slotLabel(row.posKey) : '选格' }}
                    </button>
                    <span v-if="row.status === 'ok'" class="mono text-[11px] font-bold text-center" style="color: var(--success)">✓</span>
                    <span v-else-if="row.status === 'err'" class="mono text-[11px] font-bold text-center" :title="row.err" style="color: var(--danger)">✗</span>
                    <span v-else class="mono text-[10px] text-center" style="color: var(--text-faint)">…</span>
                    <button v-if="row.status !== 'ok' && !row.supplierPart.trim()"
                            class="icon-btn !h-6 !w-6" title="识别料号"
                            :disabled="idBusy" @click="identifyRow(row)">
                      <ScanSearch :size="13" />
                    </button>
                    <span v-else />
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
                  <span v-if="idBusy || idTotal" class="chip num !text-[11px]">
                    识别 {{ idDone }}/{{ idTotal }}
                  </span>
                  <button v-if="idBusy" class="btn !py-1.5 text-xs" @click="idStop = true">停止</button>
                  <div class="flex-1" />
                  <button class="btn btn-ghost" @click="emit('close')">关闭</button>
                  <button class="btn !py-1.5 text-xs" :disabled="busy || idBusy" @click="identifyAll">
                    <ScanSearch :size="14" /> 识别料号
                  </button>
                  <button class="btn btn-primary" :disabled="busy" @click="importAll">
                    <ListPlus :size="15" /> 全部入库
                  </button>
                </div>
              </div>
              </div>
              </template>
              </MotionPanel>
            </DialogPanel>
          </TransitionChild>
        </div>
      </div>
    </Dialog>
  </TransitionRoot>
</template>
