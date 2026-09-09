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
import AppSettingsDialog from './components/AppSettingsDialog.vue'
import GuideOverlay from './components/GuideOverlay.vue'

const bins = useBinsStore()
const connection = useConnectionStore()

const editOpen = ref(false)
const editComp = ref<ComponentItem | null>(null)
const createPos = ref<BinPosition | null>(null)
const bomOpen = ref(false)
const layoutOpen = ref(false)
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

function editComponent(comp: ComponentItem) {
  editComp.value = comp
  createPos.value = null
  editOpen.value = true
}

function createComponent(pos: BinPosition) {
  editComp.value = null
  createPos.value = pos
  editOpen.value = true
}

function startGuide(steps: BomStep[]) {
  if (!steps.length) return
  bomOpen.value = false
  guideSteps.value = steps
  guideOpen.value = true
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
        <div class="mt-2 text-[13px] leading-relaxed" style="color: var(--text-dim)">
          {{ fatal }}<br />
          请先启动后端：<code class="mono">backend/.venv/Scripts/python.exe -m uvicorn app.main:app --port 8765</code>
        </div>
        <button class="btn btn-primary mt-5" @click="retry">重试</button>
      </div>

      <GridView v-else @edit="editComponent" @create="createComponent" />
    </main>

    <!-- 对话框 -->
    <EditDialog
      :open="editOpen"
      :comp="editComp"
      :create-pos="createPos"
      :layout="bins.layout"
      @close="editOpen = false"
    />
    <BomDialog :open="bomOpen" @close="bomOpen = false" @start="startGuide" />
    <LayoutDialog :open="layoutOpen" @close="layoutOpen = false" />
    <AppSettingsDialog :open="settingsOpen" @close="settingsOpen = false" />
    <GuideOverlay
      :open="guideOpen"
      :steps="guideSteps"
      @close="guideOpen = false"
      @finished="refreshAfterGuide"
    />
  </div>
</template>