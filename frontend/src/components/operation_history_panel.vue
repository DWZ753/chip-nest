<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { History, Undo2 } from '@lucide/vue'
import { api } from '../api/client'
import type { TransactionRow } from '../api/types'
import { useBinsStore } from '../stores/bins'

const bins = useBinsStore()
const loading = ref(false)
const transactions = ref<TransactionRow[]>([])
// 撤销上一步：显示"将要撤销什么"，点一下按快照还原
const undoLabel = ref('')
const undoMsg = ref<string | null>(null)
const undoBusy = ref(false)

async function loadUndo() {
  try {
    undoLabel.value = (await api.peekUndo()).label ?? ''
  } catch {
    undoLabel.value = ''
  }
}

async function runUndo() {
  if (undoBusy.value) return
  undoBusy.value = true
  undoMsg.value = null
  try {
    const res = await api.undoLast()
    const extra = res.message && res.message !== '已还原'
      ? `（${res.message}）` : ''
    undoMsg.value = res.ok ? `已撤销：${res.label}${extra}` : res.message
    await bins.refreshAll()
    await loadUndo()
    transactions.value = await api.listTransactions(30)
  } catch (e) {
    undoMsg.value = e instanceof Error ? e.message : String(e)
  } finally {
    undoBusy.value = false
  }
}
const kindLabel: Record<string, { text: string; color: string }> = {
  create: { text: '建档', color: 'var(--info)' },
  in: { text: '入库', color: 'var(--success)' },
  out: { text: '出库', color: 'var(--warn)' },
  bom_pick: { text: '取料', color: 'var(--accent-strong)' },
  adjust: { text: '修改', color: 'var(--info)' },
  delete: { text: '删除', color: 'var(--danger)' },
  backup: { text: '备份', color: 'var(--info)' },
}

onMounted(async () => {
  loading.value = true
  try {
    transactions.value = await api.listTransactions(30)
    await loadUndo()
  } catch (e) {
    undoMsg.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <!-- 操作记录 -->
  <section class="rounded-2xl p-4" :aria-busy="loading"
           style="background: var(--panel); border: 1px solid var(--line)">
    <div class="mb-2 flex items-center gap-2 text-[13px] font-extrabold">
      <History :size="15" style="color: var(--accent-strong)" /> 操作记录
      <button class="btn ml-auto !py-1 text-[11.5px]" :disabled="undoBusy || !undoLabel"
              @click="runUndo">
        <Undo2 :size="13" class="mr-1 inline" />撤销上一步
      </button>
    </div>
    <div v-if="undoLabel" class="mb-2 truncate text-[11.5px]" style="color: var(--text-dim)">
      将撤销：{{ undoLabel }}
    </div>
    <div v-if="undoMsg" class="mb-2 text-[11.5px] font-semibold" style="color: var(--success)">
      {{ undoMsg }}
    </div>
    <div v-if="loading" class="py-4 text-center text-xs" style="color: var(--text-faint)">加载中…</div>
    <ul v-else class="flex max-h-64 flex-col gap-1 overflow-y-auto pr-1">
      <li v-for="t in transactions" :key="t.id"
          class="flex items-center gap-2 rounded-lg px-2 py-1 text-[12px]">
        <span class="chip !text-[10px]"
              :style="'color:' + (kindLabel[t.kind]?.color ?? 'var(--text-dim)')">
          {{ kindLabel[t.kind]?.text ?? t.kind }}
        </span>
        <span class="truncate" style="color: var(--text-dim)">{{ t.detail ?? '' }}</span>
        <span class="ml-auto num font-bold"
              :style="t.delta > 0 ? 'color: var(--success)' : t.delta < 0 ? 'color: var(--danger)' : ''">
          {{ t.delta > 0 ? '+' : '' }}{{ t.delta }}
        </span>
      </li>
      <li v-if="!transactions.length" class="py-3 text-center text-xs" style="color: var(--text-faint)">
        暂无操作记录
      </li>
    </ul>
  </section>
</template>
