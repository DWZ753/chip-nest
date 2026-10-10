<script setup lang="ts">
import { onMounted, ref } from 'vue'

import type { BomStep, ComponentItem } from './api/types'
import { useBinsStore, type BinPosition } from './stores/bins'
import { useConnectionStore } from './stores/connection'
import TopBar from './components/TopBar.vue'
import GridView from './components/GridView.vue'
import EditDialog from './components/EditDialog.vue'
import BomDialog from './components/BomDialog.vue'
import LayoutDialog from './components/LayoutDialog.vue'
import ManualStockDialog from './components/ManualStockDialog.vue'
import AppSettingsDialog from './components/AppSettingsDialog.vue'
import GuideOverlay from './components/GuideOverlay.vue'

const bins = useBinsStore()
const connection = useConnectionStore()
const gridView = ref<InstanceType<typeof GridView> | null>(null)

const editOpen = ref(false)
const editComp = ref<ComponentItem | null>(null)
const editPos = ref<BinPosition | null>(null)
const createPos = ref<BinPosition | null>(null)
const bomOpen = ref(false)
const layoutOpen = ref(false)
const manualOpen = ref(false)
const pending_dialog = ref<'manual' | 'inventory' | null>(null)
const settingsOpen = ref(false)
const guideOpen = ref(false)
const guideSteps = ref<BomStep[]>([])
const fatal = ref<string | null>(null)

onMounted(async () => {
  connection.connect()
  void connection.fetchHealth()
  try {
    await bins.refreshAll()
  } catch (e) {
    fatal.value = e instanceof Error ? e.message : String(e)
  }
})

function editComponent(comp: ComponentItem, pos: BinPosition) {
  editComp.value = comp
  editPos.value = pos
  createPos.value = null
  editOpen.value = true
}

function createComponent(pos: BinPosition) {
  editComp.value = null
  editPos.value = null
  createPos.value = pos
  editOpen.value = true
}

function startGuide(steps: BomStep[]) {
  if (!steps.length) return
  bomOpen.value = false
  guideSteps.value = steps
  guideOpen.value = true
}

function openManual() {
  pending_dialog.value = 'manual'
  bomOpen.value = false
}

function closeManual() {
  pending_dialog.value = 'inventory'
  manualOpen.value = false
}

/** 上一个窗口关闭后再打开目标窗口，避免焦点锁相互争抢。 */
function finish_dialog_switch(target: 'manual' | 'inventory') {
  if (pending_dialog.value !== target) return
  pending_dialog.value = null
  if (target === 'manual') manualOpen.value = true
  else bomOpen.value = true
}

// 一键清空之后：收掉引导/BOM 弹窗，清检索词并重拉整个网格
async function afterWipe() {
  guideOpen.value = false
  bomOpen.value = false
  try { await bins.resetAfterWipe() } catch { /* 下次操作自愈 */ }
}

async function refreshAfterGuide() {
  try { await bins.refreshAll() } catch { /* 下次操作自愈 */ }
}

async function retry() {
  fatal.value = null
  try {
    await bins.refreshAll()
  } catch (e) {
    fatal.value = e instanceof Error ? e.message : String(e)
  }
}
</script>

<template>
  <div class="flex h-full flex-col gap-4 pt-3">
    <TopBar
      @open-bom="bomOpen = true"
      @open-layout="layoutOpen = true"
      @open-settings="settingsOpen = true"
    />

    <main class="min-h-0 flex-1 overflow-y-auto">
      <div v-if="fatal" class="glass-panel mx-auto mt-10 w-[min(560px,90%)] rounded-3xl p-6 text-center">
        <div class="text-lg font-extrabold" style="color: var(--danger)">后端不可用</div>
        <div class="mt-2 break-all text-[13px] leading-relaxed" style="color: var(--text-dim)">{{ fatal }}</div>
        <button class="btn btn-primary mt-5" @click="retry">重试</button>
      </div>

      <GridView v-else ref="gridView"
                @edit="editComponent" @create="createComponent" />
    </main>

    <!-- 对话框 -->
    <EditDialog
      :open="editOpen"
      :comp="editComp"
      :edit-pos="editPos"
      :create-pos="createPos"
      :layout="bins.layout"
      @close="editOpen = false"
      @locate-primary="gridView?.locatePrimary($event)"
    />
    <BomDialog
      :open="bomOpen"
      @close="bomOpen = false"
      @manual="openManual"
      @start="startGuide"
      @after-leave="finish_dialog_switch('manual')"
    />
    <LayoutDialog
      :open="layoutOpen"
      @close="layoutOpen = false"
    />
    <ManualStockDialog :open="manualOpen" @close="closeManual"
                       @after-leave="finish_dialog_switch('inventory')" />
    <AppSettingsDialog
      :open="settingsOpen"
      @close="settingsOpen = false"
      @reset="afterWipe"
      @refresh="refreshAfterGuide"
    />
    <GuideOverlay
      :open="guideOpen"
      :steps="guideSteps"
      @close="guideOpen = false"
      @finished="refreshAfterGuide"
    />
  </div>
</template>
