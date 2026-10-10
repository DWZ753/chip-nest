<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  Dialog, DialogPanel, DialogTitle, TransitionChild, TransitionRoot,
} from '@headlessui/vue'
import {
  FileUp, Lamp, Link2, ListOrdered, MonitorCog, Moon, Palette, Sun,
  Download, Trash2, X,
} from '@lucide/vue'

import { api } from '../api/client'
import type {
  BackupResult, BackupSnapshot, DataSummary, ResetResult,
  RestoreResult,
} from '../api/types'
import { useConnectionStore } from '../stores/connection'
import { useTheme } from '../stores/theme'
import MotionTabs from './ui/motion_tabs.vue'
import MotionPanel from './ui/motion_panel.vue'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ close: []; reset: []; refresh: [] }>()
const connection = useConnectionStore()
const {
  dark, setLight, fontScale, setFontScale, FONT_STEPS, mergeSlots, setMergeSlots,
} = useTheme()
const active_tab = ref('appearance')
const tabs = [
  { key: 'appearance', label: '外观' },
  { key: 'hardware', label: '硬件' },
  { key: 'backup', label: '备份与恢复' },
  { key: 'cleanup', label: '数据清理' },
  { key: 'about', label: '关于' },
]

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

const backupBusy = ref(false)
const backupError = ref<string | null>(null)
const createdBackup = ref<BackupResult | null>(null)

const backup = ref<BackupSnapshot | null>(null)
const backupName = ref('')
const restoreConfirming = ref(false)
const restoreConfirmText = ref('')
const restoreBusy = ref(false)
const restoreError = ref<string | null>(null)
const restored = ref<RestoreResult | null>(null)
const canRestore = computed(() => !restoreBusy.value
  && restoreConfirmText.value.trim() === '恢复')

async function createBackup() {
  if (backupBusy.value || busy.value || restoreBusy.value) return
  backupBusy.value = true
  backupError.value = null
  createdBackup.value = null
  try {
    createdBackup.value = await api.createBackup()
    await loadSummary()
    emit('refresh')
  } catch (e) {
    backupError.value = e instanceof Error ? e.message : String(e)
  } finally {
    backupBusy.value = false
  }
}

function downloadBackup() {
  if (!createdBackup.value) return
  const result = createdBackup.value
  const blob = new Blob([JSON.stringify(result.backup, null, 2)], {
    type: 'application/json;charset=utf-8',
  })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = result.backup_path.split(/[\\/]/).pop() ?? 'chipnest-backup.json'
  document.body.appendChild(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

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
  if (!canConfirm.value || backupBusy.value || restoreBusy.value) return
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

async function onBackupFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  backup.value = null
  backupName.value = ''
  restoreConfirming.value = false
  restoreConfirmText.value = ''
  restoreError.value = null
  restored.value = null
  try {
    const parsed: unknown = JSON.parse(await file.text())
    if (!parsed || typeof parsed !== 'object'
        || !('app' in parsed) || parsed.app !== 'ChipNest'
        || !('components' in parsed) || !Array.isArray(parsed.components)
        || !('transactions' in parsed) || !Array.isArray(parsed.transactions)) {
      throw new Error('备份文件无效')
    }
    backup.value = parsed as BackupSnapshot
    backupName.value = file.name
  } catch {
    restoreError.value = '备份文件无效'
  }
}

function startRestoreConfirm() {
  restoreConfirmText.value = ''
  restoreError.value = null
  restoreConfirming.value = true
}

function cancelRestore() {
  restoreConfirming.value = false
  restoreConfirmText.value = ''
  restoreError.value = null
}

async function doRestore() {
  if (!canRestore.value || !backup.value || backupBusy.value || busy.value) return
  restoreBusy.value = true
  restoreError.value = null
  try {
    restored.value = await api.restoreData({
      confirm: restoreConfirmText.value.trim(),
      backup: backup.value,
    })
    backup.value = null
    backupName.value = ''
    restoreConfirming.value = false
    restoreConfirmText.value = ''
    await loadSummary()
    emit('reset')
  } catch (e) {
    restoreError.value = e instanceof Error ? e.message : String(e)
  } finally {
    restoreBusy.value = false
  }
}

// 打开时取一次概况（决定按钮能不能点）；关上则收起确认态与上次的结果提示
watch(() => props.open, (open) => {
  if (open) {
    active_tab.value = 'appearance'
    void loadSummary()
    return
  }
  confirming.value = false
  confirmText.value = ''
  resetError.value = null
  wiped.value = null
  backupError.value = null
  createdBackup.value = null
  backup.value = null
  backupName.value = ''
  restoreConfirming.value = false
  restoreConfirmText.value = ''
  restoreError.value = null
  restored.value = null
})
</script>

<template>
  <TransitionRoot :show="open" as="template">
    <Dialog as="div" class="relative z-50" @close="emit('close')">
      <TransitionChild as="template" enter="dialog-backdrop-enter"
                       enter-from="opacity-0" enter-to="opacity-100"
                       leave="dialog-backdrop-leave" leave-to="opacity-0">
        <div class="fixed inset-0 bg-black/60 backdrop-blur-[6px]" />
      </TransitionChild>
      <div class="fixed inset-0 overflow-y-auto">
        <div class="flex min-h-full items-center justify-center p-4">
          <TransitionChild as="template" enter="dialog-panel-enter"
                           enter-from="dialog-panel-from"
                           enter-to="dialog-panel-visible"
                           leave="dialog-panel-leave"
                           leave-to="dialog-panel-to">
            <DialogPanel class="glass-strong flex max-h-[88vh] w-full max-w-md flex-col rounded-2xl p-5">
              <div class="mb-4 flex items-center gap-2.5">
                <Palette :size="17" style="color: var(--accent)" />
                <DialogTitle class="text-base font-extrabold">设置</DialogTitle>
                <button class="icon-btn ml-auto !h-8 !w-8" @click="emit('close')"><X :size="16" /></button>
              </div>

              <MotionTabs v-model="active_tab" :tabs="tabs" label="设置分组" />
              <MotionPanel>
              <div class="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto pr-1">
                <div :key="active_tab" class="panel-reveal flex flex-col gap-4">
                <div v-if="active_tab === 'appearance'" class="flex flex-col gap-4">
                <!-- 外观 -->
                <section class="rounded-2xl p-4" style="background: var(--panel); border: 1px solid var(--line)">
                  <div class="mb-3 flex items-center gap-2 text-[13px] font-extrabold">
                    <Sun :size="14" style="color: var(--accent-strong)" /> 主题
                  </div>
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
                  </div>
                </section>

                <!-- 格子显示：占用格是合并成一张大卡，还是各显示一张共用卡 -->
                <section class="rounded-2xl p-4" style="background: var(--panel); border: 1px solid var(--line)">
                  <div class="mb-3 flex items-center gap-2 text-[13px] font-extrabold">
                    <Link2 :size="14" style="color: var(--accent-strong)" /> 卡片
                  </div>
                  <div class="flex flex-wrap items-center gap-3">
                    <button
                      class="chip !cursor-pointer !px-3 !py-1.5"
                      :class="mergeSlots ? '' : 'opacity-55'"
                      :style="mergeSlots ? 'color: var(--accent); border-color: var(--accent)' : ''"
                      @click="setMergeSlots(true)"
                    >合并渲染</button>
                    <button
                      class="chip !cursor-pointer !px-3 !py-1.5"
                      :class="mergeSlots ? 'opacity-55' : ''"
                      :style="mergeSlots ? '' : 'color: var(--accent); border-color: var(--accent)'"
                      @click="setMergeSlots(false)"
                    >分开渲染</button>
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

                </div>
                <div v-else-if="active_tab === 'hardware'" class="flex flex-col gap-4">
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

                </div>
                <section v-else-if="active_tab === 'backup'" class="rounded-2xl p-4" style="background: var(--panel); border: 1px solid var(--line)">
                  <h3 class="mb-3 text-[13px] font-extrabold">备份与恢复</h3>
                  <div class="pb-4">
                    <button class="btn !py-1.5 text-xs"
                            :disabled="backupBusy || busy || restoreBusy"
                            @click="createBackup">
                      {{ backupBusy ? '正在备份…' : '创建备份' }}
                    </button>
                    <template v-if="createdBackup">
                      <div class="mt-2 text-[11.5px]" style="color: var(--success)">
                        已备份 {{
                          createdBackup.backup.components.length
                        }} 个元件、{{
                          createdBackup.backup.transactions.length
                        }} 条流水
                      </div>
                      <div class="mono mt-1 break-all text-[10.5px]"
                           style="color: var(--text-faint)">
                        {{ createdBackup.backup_path }}
                      </div>
                      <button class="btn btn-ghost mt-2 !py-1.5 text-xs"
                              @click="downloadBackup">
                        <Download :size="14" class="mr-1 inline" />下载备份
                      </button>
                    </template>
                    <div v-if="backupError" class="mt-2 text-[11.5px] font-bold"
                         style="color: var(--danger)">{{ backupError }}</div>
                  </div>

                  <div class="mt-4 border-t pt-4" style="border-color: var(--line)">
                    <div class="mb-2 text-[12.5px] font-bold">恢复备份</div>
                    <label class="btn inline-flex cursor-pointer !py-1.5 text-xs"
                           :class="{
                             'pointer-events-none opacity-50':
                               restoreBusy || backupBusy || busy,
                           }">
                      <FileUp :size="14" class="mr-1 inline" />选择 JSON 备份
                      <input class="hidden" type="file" accept=".json,application/json"
                             :disabled="restoreBusy || backupBusy || busy"
                             @change="onBackupFile" />
                    </label>
                    <div v-if="backup" class="mt-2 text-[11.5px]" style="color: var(--text-dim)">
                      <div class="truncate">{{ backupName }}</div>
                      <div class="mt-1">{{ backup.components.length }} 个元件 · {{ backup.transactions.length }} 条流水 · {{ backup.blocked_slots?.length ?? 0 }} 个停用格</div>
                    </div>
                    <div v-if="restored" class="mt-2 text-[11.5px]" style="color: var(--success)">
                      已恢复 {{ restored.components }} 个元件、{{ restored.transactions }} 条流水
                    </div>
                    <div v-if="restored" class="mono mt-1 break-all text-[10.5px]"
                         style="color: var(--text-faint)">{{ restored.backup_path }}</div>
                    <div v-if="restoreError" class="mt-2 text-[11.5px] font-bold"
                         style="color: var(--danger)">{{ restoreError }}</div>
                    <div v-if="restoreConfirming" class="mt-3 rounded-xl p-3 text-[12px]"
                         style="background: rgba(255, 92, 122, 0.08); border: 1px solid rgba(255, 92, 122, 0.34)">
                      <div class="font-bold" style="color: var(--danger)">将覆盖当前数据</div>
                      <div class="field-label mt-3">确认词</div>
                      <input v-model="restoreConfirmText" class="input mt-1.5" placeholder="恢复"
                             maxlength="4" @keyup.enter="doRestore" />
                      <div class="mt-3 flex items-center gap-2">
                        <button class="btn btn-danger"
                                :disabled="!canRestore || backupBusy || busy"
                                @click="doRestore">
                          {{ restoreBusy ? '正在恢复…' : '确认恢复' }}
                        </button>
                        <button class="btn btn-ghost" :disabled="restoreBusy" @click="cancelRestore">取消</button>
                      </div>
                    </div>
                    <button v-else-if="backup" class="btn btn-danger mt-3 !py-1.5 text-xs"
                            :disabled="restoreBusy || backupBusy || busy"
                            @click="startRestoreConfirm">恢复备份</button>
                  </div>
                </section>
                <section v-else-if="active_tab === 'cleanup'" class="rounded-2xl p-4" style="background: var(--panel); border: 1px solid var(--line)">
                  <h3 class="mb-3 text-[13px] font-extrabold" style="color: var(--danger)">数据清理</h3>
                  <template v-if="!confirming">
                    <button class="btn btn-danger"
                            :disabled="!canWipe || backupBusy || restoreBusy"
                            @click="startConfirm">
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
                        <button class="btn btn-danger"
                                :disabled="!canConfirm || backupBusy || restoreBusy"
                                @click="doReset">
                          {{ busy ? '正在清空…' : '确认清空' }}
                        </button>
                        <button class="btn btn-ghost" :disabled="busy" @click="cancelConfirm">取消</button>
                      </div>
                    </div>
                  </template>

                </section>
                <div v-else>
                <!-- 版本 -->
                <section class="flex items-center justify-between rounded-2xl px-4 py-3 text-[12.5px]"
                         style="background: var(--panel); border: 1px solid var(--line)">
                  <span class="font-bold">版本</span>
                  <span class="mono font-bold" style="color: var(--accent)">
                    {{ connection.version ? 'v' + connection.version : '—' }}
                  </span>
                </section>

                </div>
                </div>
              </div>
              </MotionPanel>

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
