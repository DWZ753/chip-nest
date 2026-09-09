<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import {
  Dialog, DialogPanel, DialogTitle, TransitionChild, TransitionRoot,
} from '@headlessui/vue'
import { History, LayoutGrid, PackagePlus, Save, X } from '@lucide/vue'

import { api } from '../api/client'
import type { TransactionRow } from '../api/types'
import { useBinsStore } from '../stores/bins'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ close: []; manual: [] }>()
const bins = useBinsStore()

const form = reactive({
  zone_count: 1, layer_count: 3, row_count: 1, col_count: 4,
  zone_names: [''] as string[],
})
const transactions = ref<TransactionRow[]>([])
const loading = ref(false)
const saving = ref(false)
const msg = ref<string | null>(null)

watch(
  () => props.open,
  async (v) => {
    if (!v) return
    form.zone_count = bins.layout.zone_count
    form.layer_count = bins.layout.layer_count
    form.row_count = bins.layout.row_count
    form.col_count = bins.layout.col_count
    form.zone_names = Array.from({ length: form.zone_count }, (_, i) =>
      (bins.layout.zone_names?.[i] ?? '').slice(0, 24))
    msg.value = null
    loading.value = true
    try { transactions.value = await api.listTransactions(30) }
    finally { loading.value = false }
  },
)

async function saveLayout() {
  saving.value = true
  msg.value = null
  try {
    const names = Array.from({ length: form.zone_count }, (_, i) =>
      (form.zone_names[i] ?? '').trim().slice(0, 24))
    await api.putLayout({
      zone_count: form.zone_count, layer_count: form.layer_count,
      row_count: form.row_count, col_count: form.col_count,
      zone_names: names,
    })
    await bins.refreshAll()
    msg.value = '已保存'
    window.setTimeout(() => (msg.value = null), 1500)
  } catch (e) {
    msg.value = e instanceof Error ? e.message : String(e)
  } finally { saving.value = false }
}

const kindLabel: Record<string, { text: string; color: string }> = {
  create: { text: '建档', color: 'var(--info)' },
  in: { text: '入库', color: 'var(--success)' },
  out: { text: '出库', color: 'var(--warn)' },
  bom_pick: { text: '取料', color: 'var(--accent-strong)' },
  adjust: { text: '修改', color: 'var(--info)' },
  delete: { text: '删除', color: 'var(--danger)' },
}
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
            <DialogPanel class="glass-strong flex max-h-[88vh] w-full max-w-xl flex-col rounded-2xl p-5">
              <div class="mb-4 flex items-center gap-2.5">
                <LayoutGrid :size="17" style="color: var(--accent)" />
                <DialogTitle class="text-base font-extrabold">仓库布局</DialogTitle>
                <button class="btn ml-auto !px-3 !py-1.5 text-xs" @click="emit('manual')">
                  <PackagePlus :size="14" /> 手工入库
                </button>
                <button class="icon-btn !h-8 !w-8" @click="emit('close')"><X :size="16" /></button>
              </div>

              <div class="flex flex-col gap-4 overflow-y-auto pr-1">
                <!-- 网格尺寸与区名 -->
                <section class="rounded-2xl p-4" style="background: var(--panel); border: 1px solid var(--line)">
                  <div class="mb-3 flex items-center gap-2 text-[13px] font-extrabold">
                    货架网格
                    <span class="chip num ml-auto">{{ form.row_count * form.col_count }} 格/层</span>
                  </div>
                  <div class="grid grid-cols-4 gap-2.5">
                    <div v-for="f in [
                      ['区数', 'zone_count'], ['层数', 'layer_count'],
                      ['行数', 'row_count'], ['列数', 'col_count']] as const" :key="f[1]">
                      <label class="field-label">{{ f[0] }}</label>
                      <input v-model.number="form[f[1]]" class="input num text-center" type="number" min="1" />
                    </div>
                  </div>
                  <div v-if="form.zone_count >= 1" class="mt-3 grid gap-2"
                       :style="{ gridTemplateColumns: 'repeat(' + Math.min(form.zone_count, 3) + ', minmax(0,1fr))' }">
                    <div v-for="z in form.zone_count" :key="z">
                      <label class="field-label">区{{ z }}名称</label>
                      <input v-model="form.zone_names[z - 1]" class="input !py-1.5 text-[13px]"
                             maxlength="24" placeholder="留空则显示第 {{ z }} 区" />
                    </div>
                  </div>
                  <div class="mt-3 flex items-center gap-2">
                    <span v-if="msg" class="text-[12.5px] font-semibold"
                          :style="msg === '已保存' ? 'color: var(--success)' : 'color: var(--danger)'">{{ msg }}</span>
                    <div class="flex-1" />
                    <button class="btn btn-primary !py-1.5 text-xs" :disabled="saving" @click="saveLayout">
                      <Save :size="14" /> 保存
                    </button>
                  </div>
                </section>

                <!-- 最近操作 -->
                <section class="rounded-2xl p-4" style="background: var(--panel); border: 1px solid var(--line)">
                  <div class="mb-2 flex items-center gap-2 text-[13px] font-extrabold">
                    <History :size="15" style="color: var(--accent-strong)" /> 最近操作
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
              </div>

              <div class="mt-4 flex justify-end">
                <button class="btn btn-ghost" @click="emit('close')">关闭</button>
              </div>
            </DialogPanel>
          </TransitionChild>
        </div>
      </div>
    </Dialog>
  </TransitionRoot>
</template>