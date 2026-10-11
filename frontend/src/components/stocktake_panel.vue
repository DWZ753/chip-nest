<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ClipboardCheck, RefreshCw } from '@lucide/vue'
import { api } from '../api/client'
import type { ComponentItem, StocktakeEntry } from '../api/types'
import { useBinsStore, zoneName } from '../stores/bins'

const bins = useBinsStore()
const rows = ref<{ component: ComponentItem; actual: number | '' }[]>([])
const query = ref('')
const note = ref('')
const busy = ref(false)
const confirming = ref(false)
const message = ref('')
const error = ref('')
const visible = computed(() => rows.value.filter(row => confirming.value
  ? row.actual !== '' && row.actual !== row.component.quantity
  : [row.component.name, row.component.value, row.component.package,
    row.component.manufacturer_part, row.component.supplier_part]
    .join(' ').toLowerCase().includes(query.value.trim().toLowerCase())))
const entries = computed<StocktakeEntry[]>(() => rows.value
  .filter(row => row.actual !== '')
  .map(row => ({ component_id: row.component.id,
    expected_quantity: row.component.quantity, quantity: Number(row.actual) })))
const changed = computed(() => entries.value.filter(row =>
  row.quantity !== row.expected_quantity))
const valid = computed(() => entries.value.every(row =>
  Number.isSafeInteger(row.quantity) && row.quantity >= 0))

/** 重新读取账面库存并开始一轮新的盘点。 */
async function load() {
  busy.value = true
  error.value = ''
  confirming.value = false
  try {
    await bins.refreshAll()
    rows.value = bins.components.map(component =>
      ({ component: { ...component }, actual: '' }))
  } catch (e) { error.value = e instanceof Error ? e.message : String(e) }
  finally { busy.value = false }
}

/** 确认差异后整体提交，失败保留已填的实盘数量。 */
async function apply() {
  if (!valid.value || !changed.value.length || busy.value) return
  if (!confirming.value) { confirming.value = true; return }
  busy.value = true
  error.value = ''
  try {
    const result = await api.stocktake(entries.value, note.value)
    const count = entries.value.length
    note.value = ''
    await load()
    message.value = `已盘点 ${count} 个元件，校正 ${result.changed} 个`
  } catch (e) { error.value = e instanceof Error ? e.message : String(e) }
  finally { busy.value = false; confirming.value = false }
}
onMounted(load)
</script>

<template>
  <section class="flex min-h-0 flex-col gap-3 rounded-2xl p-4"
           style="background: var(--panel); border: 1px solid var(--line)">
    <div class="flex items-center gap-2">
      <ClipboardCheck :size="16" style="color: var(--accent-strong)" />
      <h3 class="text-sm font-extrabold">库存盘点</h3>
      <span class="chip ml-auto">已填 {{ entries.length }} · 差异 {{ changed.length }}</span>
      <button class="icon-btn" title="刷新库存" :disabled="busy" @click="load">
        <RefreshCw :size="15" />
      </button>
    </div>
    <input v-model="query" class="input" placeholder="搜索元件" aria-label="盘点搜索" />
    <div class="max-h-[46vh] overflow-auto rounded-xl"
         style="border: 1px solid var(--line)">
      <table class="w-full text-left text-xs">
        <thead class="sticky top-0" style="background: var(--surface-2)">
          <tr><th class="p-3">元件 / 主格</th><th class="p-3 text-right">账面</th>
            <th class="p-3 text-right">实盘</th><th class="p-3 text-right">差异</th></tr>
        </thead>
        <tbody>
          <tr v-for="row in visible" :key="row.component.id"
              style="border-top: 1px solid var(--line)">
            <td class="p-3">
              <div class="font-bold">{{ row.component.name }}
                <span class="mono font-normal">{{ row.component.value }} {{ row.component.package }}</span>
              </div>
              <div class="mt-1" style="color: var(--text-faint)">
                {{ zoneName(bins.layout, row.component.zone) }}/{{ row.component.layer }}层/{{ row.component.slot }}格
                · {{ row.component.slot_count }} 格
              </div>
            </td>
            <td class="num p-3 text-right">{{ row.component.quantity }}</td>
            <td class="p-2 text-right">
              <input v-model.number="row.actual" type="number" min="0" step="1"
                     class="input num w-24 !py-1.5 text-right"
                     :aria-label="row.component.name + '实盘数量'" :disabled="busy"
                     @input="confirming = false; message = ''" />
            </td>
            <td class="num p-3 text-right" :style="{ color:
              Number(row.actual) < row.component.quantity ? 'var(--danger)' : 'var(--success)' }">
              {{ row.actual === '' ? '—' : Number(row.actual) - row.component.quantity }}
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="!visible.length" class="p-5 text-center text-xs">没有元件</div>
    </div>
    <input v-model="note" class="input" placeholder="盘点备注" maxlength="200" />
    <div v-if="message" class="text-xs" style="color: var(--success)">{{ message }}</div>
    <div v-if="error || !valid" class="text-xs" style="color: var(--danger)">
      {{ error || '实盘数量无效' }}
    </div>
    <div class="flex justify-end gap-2">
      <button v-if="confirming" class="btn btn-ghost" :disabled="busy"
              @click="confirming = false">取消</button>
      <button class="btn btn-primary" :disabled="busy || !valid || !changed.length"
              @click="apply">{{ confirming ? '确认校正' : '核对差异' }}</button>
    </div>
  </section>
</template>
