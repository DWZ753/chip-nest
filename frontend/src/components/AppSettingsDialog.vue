<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  Dialog, DialogPanel, DialogTitle, TransitionChild, TransitionRoot,
} from '@headlessui/vue'
import {
  DatabaseZap, Lamp, Link2, ListOrdered, Layers, MonitorCog, Moon, Palette, Sun,
  Trash2, X,
} from '@lucide/vue'

import { api } from '../api/client'
import type { DataSummary, MergeGroup, ResetResult } from '../api/types'
import { useConnectionStore } from '../stores/connection'
import { useTheme } from '../stores/theme'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ close: []; reset: []; refresh: [] }>()
const connection = useConnectionStore()
const {
  dark, setLight, fontScale, setFontScale, FONT_STEPS, mergeSlots, setMergeSlots,
} = useTheme()
const SCALE_LABELS = ['小', '中', '大', '特大']

const MODE_TEXT = {
  serial: '串口模式',
  mock: '模拟模式',
} as Record<string, string>

// ---- 灯带序号重排 ----
const ledBusy = ref(false)
const ledNote = ref<string | null>(null)
const ledError = ref<string | null>(null)

async function reindexLeds() {
  if (ledBusy.value) return
  ledBusy.value = true
  ledNote.value = null
  ledError.value = null
  try {
    const res = await api.reindexLeds()
    ledNote.value = res.changed
      ? `已重排 ${res.total} 个元件，${res.changed} 个序号有变动`
      : `${res.total} 个元件序号本来就是对的`
    emit('refresh')
  } catch (e) {
    ledError.value = e instanceof Error ? e.message : String(e)
  } finally {
    ledBusy.value = false
  }
}

// ---- 合并重复元件（同名 + 同标称值 + 同封装）----
const mergeBusy = ref(false)
const mergeGroups = ref<MergeGroup[]>([])
const mergeNote = ref<string | null>(null)

async function previewMerge() {
  mergeBusy.value = true
  mergeNote.value = null
  mergeGroups.value = []
  try {
    const res = await api.mergeDuplicates(true)
    mergeGroups.value = res.groups
    if (!res.groups.length) mergeNote.value = '没有可合并的重复元件'
  } catch (e) {
    mergeNote.value = e instanceof Error ? e.message : String(e)
  } finally { mergeBusy.value = false }
}

async function applyMerge() {
  mergeBusy.value = true
  try {
    const res = await api.mergeDuplicates(false)
    mergeGroups.value = []
    mergeNote.value = `已合并 ${res.merged_groups} 组、${res.merged_components} 条`
    await loadSummary()
    emit('refresh')
  } catch (e) {
    mergeNote.value = e instanceof Error ? e.message : String(e)
  } finally { mergeBusy.value = false }
}

// ---- 清空所有数据 ----
// 确认词与后端 app/routers/system.py 的 RESET_CONFIRM_WORD 必须一致
const CONFIRM_WORD = '清空'
const confirming = ref(false)
const confirmText = ref('')
const resetLayout = ref(true)
const busy = ref(false)
const resetError = ref<string | null>(null)
const wiped = ref<ResetResult | null>(null)

const canConfirm = computed(() => !busy.value && confirmText.value.trim() === CONFIRM_WORD)
// 数据概况：库里啥都没有时清空按钮不可点（数量也取自这里，不受搜索筛选影响）
const summary = ref<DataSummary | null>(null)
const canWipe = computed(() => !!summary.value && !summary.value.empty)

async function loadSummary() {
  try {
    summary.value = await api.dataSummary()
  } catch {
    summary.value = null  // 取不到就不放行，避免误点
  }
}

function startConfirm() {
  confirmText.value = ''
  resetError.value = null
  wiped.value = null
  confirming.value = true
}

function cancelConfirm() {
  confirming.value = false
  confirmText.value = ''
  resetError.value = null
}

async function doReset() {
  if (!canConfirm.value) return
  busy.value = true
  resetError.value = null
  try {
    wiped.value = await api.resetData({
      confirm: confirmText.value.trim(),
      reset_layout: resetLayout.value,
    })
    confirming.value = false
    confirmText.value = ''
    await loadSummary()  // 已清空 -> 按钮随即变灰
    emit('reset')
  } catch (e) {
    resetError.value = e instanceof Error ? e.message : String(e)
  } finally {
    busy.value = false
  }
}

// 打开时取一次概况（决定按钮能不能点）；关上则收起确认态与上次的结果提示
watch(() => props.open, (open) => {
  if (open) {
    void loadSummary()
    return
  }
  confirming.value = false
  confirmText.value = ''
  resetError.value = null
  wiped.value = null
})
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
            <DialogPanel class="glass-strong flex max-h-[88vh] w-full max-w-md flex-col rounded-2xl p-5">
              <div class="mb-4 flex items-center gap-2.5">
                <Palette :size="17" style="color: var(--accent)" />
                <DialogTitle class="text-base font-extrabold">设置</DialogTitle>
                <button class="icon-btn ml-auto !h-8 !w-8" @click="emit('close')"><X :size="16" /></button>
              </div>

              <div class="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto pr-1">
                <!-- 外观 -->
                <section class="rounded-2xl p-4" style="background: var(--panel); border: 1px solid var(--line)">
                  <div class="mb-3 flex items-center gap-2 text-[13px] font-extrabold">外观</div>
                  <div class="flex flex-wrap items-center gap-3">
                    <button
                      class="chip !cursor-pointer !px-3 !py-1.5"
                      :class="dark ? 'opacity-55' : ''"
                      :style="!dark ? 'color: var(--accent); border-color: var(--accent)' : ''"
                      @click="setLight(true)"
                    ><Sun :size="12" class="mr-1 inline" />浅色</button>
                    <button
                      class="chip !cursor-pointer !px-3 !py-1.5"
                      :class="dark ? '' : 'opacity-55'"
                      :style="dark ? 'color: var(--accent); border-color: var(--accent)' : ''"
                      @click="setLight(false)"
                    ><Moon :size="12" class="mr-1 inline" />深色</button>
                    <button
                      class="chip !cursor-pointer !px-3 !py-1.5"
                      :class="mergeSlots ? '' : 'opacity-55'"
                      :style="mergeSlots ? 'color: var(--accent); border-color: var(--accent)' : ''"
                      @click="setMergeSlots(!mergeSlots)"
                    ><Link2 :size="12" class="mr-1 inline" />跨格显示</button>
                  </div>
                </section>

                <!-- 字号 -->
                <section class="rounded-2xl p-4" style="background: var(--panel); border: 1px solid var(--line)">
                  <div class="mb-3 text-[13px] font-extrabold">字号</div>
                  <div class="flex flex-wrap items-center gap-1.5">
                    <button v-for="(s, i) in FONT_STEPS" :key="s"
                            class="chip !cursor-pointer !px-3 !py-1.5"
                            :class="fontScale === s ? '' : 'opacity-55 hover:opacity-90'"
                            :style="fontScale === s ? 'color: var(--accent); border-color: var(--accent)' : ''"
                            @click="setFontScale(s)">
                      {{ SCALE_LABELS[i] }}
                    </button>
                  </div>
                </section>

                <!-- 版本 -->
                <section class="flex items-center justify-between rounded-2xl px-4 py-3 text-[12.5px]"
                         style="background: var(--panel); border: 1px solid var(--line)">
                  <span class="font-bold">版本</span>
                  <span class="mono font-bold" style="color: var(--accent)">
                    {{ connection.version ? 'v' + connection.version : '—' }}
                  </span>
                </section>

                <!-- 硬件状态 -->
                <section class="rounded-2xl px-4 py-3 text-[12.5px]"
                         style="background: var(--panel); border: 1px solid var(--line)">
                  <div class="mb-1.5 flex items-center gap-2 text-[13px] font-extrabold">
                    <MonitorCog :size="15" style="color: var(--accent-strong)" /> 硬件
                  </div>
                  <div class="flex flex-wrap items-center gap-x-4 gap-y-1.5">
                    <span class="chip"
                          :style="connection.status.mode === 'serial' ? 'color: var(--success)' : 'color: var(--warn)'">
                      {{ MODE_TEXT[connection.status.mode] ?? connection.status.mode }}
                    </span>
                    <span style="color: var(--text-dim)">设备：{{ connection.status.device ?? '—' }}</span>
                    <span style="color: var(--text-faint)">{{ connection.status.error ?? '' }}</span>
                  </div>
                </section>

                <!-- 灯带序号：按位置重排，修老库里撞号的灯 -->
                <section class="rounded-2xl p-4" style="background: var(--panel); border: 1px solid var(--line)">
                  <div class="mb-2 flex items-center gap-2 text-[13px] font-extrabold">
                    <Lamp :size="15" style="color: var(--accent-strong)" /> 灯带序号
                  </div>
                  <button class="btn !py-1.5 text-xs" :disabled="ledBusy" @click="reindexLeds">
                    <ListOrdered :size="14" class="mr-1 inline" />按位置重排
                  </button>
                  <div v-if="ledNote" class="mt-2 text-[12px] font-semibold" style="color: var(--success)">{{ ledNote }}</div>
                  <div v-if="ledError" class="mt-2 text-[12px] font-semibold" style="color: var(--danger)">{{ ledError }}</div>
                </section>

                <!-- 重复元件合并 -->
                <section class="rounded-2xl p-4" style="background: var(--panel); border: 1px solid var(--line)">
                  <div class="mb-2 flex items-center gap-2 text-[13px] font-extrabold">
                    <Layers :size="15" style="color: var(--accent-strong)" /> 重复元件
                  </div>
                  <button class="btn !py-1.5 text-xs"
                          :disabled="mergeBusy || !summary || summary.components < 2"
                          @click="previewMerge">合并重复元件</button>

                  <div v-if="mergeGroups.length" class="mt-2 flex flex-col gap-1">
                    <div v-for="g in mergeGroups" :key="g.keep_id"
                         class="flex items-center gap-2 text-[11.5px]">
                      <span class="truncate font-semibold">{{ g.name }}</span>
                      <span class="mono" style="color: var(--text-dim)">{{ g.value }} {{ g.package }}</span>
                      <span class="num ml-auto" style="color: var(--text-faint)">
                        {{ g.member_ids.length }} 条 · 合计 {{ g.total_quantity }}
                      </span>
                    </div>
                    <div class="mt-2 flex items-center gap-2">
                      <button class="btn btn-danger !py-1.5 text-xs" :disabled="mergeBusy" @click="applyMerge">
                        确认合并
                      </button>
                      <button class="btn btn-ghost !py-1.5 text-xs" @click="mergeGroups = []">取消</button>
                    </div>
                  </div>
                  <div v-else-if="mergeNote" class="mt-2 text-[12px] font-semibold"
                       style="color: var(--text-dim)">{{ mergeNote }}</div>
                </section>

                <!-- 数据：一键清空回到干净初始状态 -->
                <section class="rounded-2xl p-4" style="background: var(--panel); border: 1px solid var(--line)">
                  <div class="mb-2 flex items-center gap-2 text-[13px] font-extrabold">
                    <DatabaseZap :size="15" style="color: var(--danger)" /> 数据
                  </div>

                  <template v-if="!confirming">
                    <button class="btn btn-danger" :disabled="!canWipe" @click="startConfirm">
                      <Trash2 :size="14" class="mr-1 inline" />清空所有数据
                    </button>

                    <div v-if="wiped" class="mt-3 rounded-xl px-3 py-2 text-[12px] leading-relaxed"
                         style="background: var(--surface-2); border: 1px solid var(--line)">
                      <div class="font-bold" style="color: var(--success)">
                        已清空：删除 {{ wiped.deleted_components }} 个元件、{{ wiped.deleted_transactions }} 条操作流水{{ wiped.layout_reset ? '，布局回到初始状态' : '' }}
                      </div>
                      <div class="mt-1" style="color: var(--text-dim)">备份文件：</div>
                      <div class="mono mt-0.5 break-all" style="color: var(--text-faint)">{{ wiped.backup_path }}</div>
                    </div>
                  </template>

                  <template v-else>
                    <div class="rounded-xl p-3 text-[12px] leading-relaxed"
                         style="background: rgba(255, 92, 122, 0.08); border: 1px solid rgba(255, 92, 122, 0.34)">
                      <div class="font-bold" style="color: var(--danger)">清空不可撤销，会先自动备份</div>
                      <div class="mt-1" style="color: var(--text-dim)">
                        将删除 {{ summary?.components ?? 0 }} 个元件、{{ summary?.transactions ?? 0 }} 条操作流水。
                      </div>
                      <label class="mt-2 flex cursor-pointer items-start gap-2" style="color: var(--text-dim)">
                        <input v-model="resetLayout" type="checkbox" style="accent-color: var(--danger)" />
                        <span>同时把仓库布局恢复为 1 区 × 3 层 × 1 行 4 列</span>
                      </label>
                      <div class="field-label mt-3">确认词</div>
                      <input v-model="confirmText" class="input mt-1.5" :placeholder="CONFIRM_WORD"
                             maxlength="4" @keyup.enter="doReset" />
                      <div v-if="resetError" class="mt-2 font-bold" style="color: var(--danger)">{{ resetError }}</div>
                      <div class="mt-3 flex items-center gap-2">
                        <button class="btn btn-danger" :disabled="!canConfirm" @click="doReset">
                          {{ busy ? '正在清空…' : '确认清空' }}
                        </button>
                        <button class="btn btn-ghost" :disabled="busy" @click="cancelConfirm">取消</button>
                      </div>
                    </div>
                  </template>
                </section>
              </div>

              <div class="mt-5 flex justify-end">
                <button class="btn btn-ghost" @click="emit('close')">关闭</button>
              </div>
            </DialogPanel>
          </TransitionChild>
        </div>
      </div>
    </Dialog>
  </TransitionRoot>
</template>