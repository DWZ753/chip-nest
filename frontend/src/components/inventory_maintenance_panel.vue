<script setup lang="ts">
import { computed, ref } from 'vue'
import { Layers } from '@lucide/vue'
import { api } from '../api/client'
import type { MergeGroup } from '../api/types'
import { useBinsStore } from '../stores/bins'

const bins = useBinsStore()
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
    selected_ids.value = []
    confirming.value = false
    await bins.refreshAll()
  } catch (e) {
    mergeNote.value = e instanceof Error ? e.message : String(e)
  } finally { mergeBusy.value = false }
}

const supplier_components = computed(() =>
  bins.components.filter((comp) => !!comp.supplier_part))
const selected_ids = ref<number[]>([])
const clearing = ref(false)
const confirming = ref(false)
const clear_note = ref<string | null>(null)

/** 清理所选元件的供应商料号，保留库存和存放格。 */
async function clear_supplier_parts() {
  if (clearing.value || !selected_ids.value.length) return
  if (!confirming.value) {
    confirming.value = true
    return
  }
  clearing.value = true
  clear_note.value = null
  try {
    for (const id of selected_ids.value) {
      bins.upsert(await api.patchComponent(id, { supplier_part: '' }))
    }
    clear_note.value = `已清除 ${selected_ids.value.length} 个元件的供应商料号`
    selected_ids.value = []
  } catch (e) {
    clear_note.value = e instanceof Error ? e.message : String(e)
  } finally {
    confirming.value = false
    clearing.value = false
    await bins.refreshAll()
  }
}
</script>

<template>
  <div class="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto pr-1">
    <!-- 重复元件合并 -->
    <section class="rounded-2xl p-4" style="background: var(--panel); border: 1px solid var(--line)">
      <div class="mb-2 flex items-center gap-2 text-[13px] font-extrabold">
        <Layers :size="15" style="color: var(--accent-strong)" /> 重复元件
      </div>
      <button class="btn !py-1.5 text-xs"
              :disabled="mergeBusy || clearing || bins.components.length < 2"
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
          <button class="btn btn-danger !py-1.5 text-xs"
                  :disabled="mergeBusy || clearing" @click="applyMerge">
            确认合并
          </button>
          <button class="btn btn-ghost !py-1.5 text-xs" @click="mergeGroups = []">取消</button>
        </div>
      </div>
      <div v-else-if="mergeNote" class="mt-2 text-[12px] font-semibold"
           style="color: var(--text-dim)">{{ mergeNote }}</div>
    </section>


    <section class="rounded-2xl p-4"
             style="background: var(--panel); border: 1px solid var(--line)">
      <h3 class="mb-3 text-[13px] font-extrabold">供应商料号</h3>
      <div class="mb-3 flex flex-wrap items-center gap-2">
        <span class="chip">已选 {{ selected_ids.length }} 个</span>
        <button class="btn !py-1.5 text-xs" :disabled="clearing || mergeBusy"
                @click="selected_ids = supplier_components.map((comp) => comp.id);
                  confirming = false">全选</button>
        <button class="btn btn-ghost !py-1.5 text-xs"
                :disabled="clearing || mergeBusy"
                @click="selected_ids = []; confirming = false">清空选择</button>
        <button class="btn btn-danger !py-1.5 text-xs"
                :disabled="!selected_ids.length || clearing || mergeBusy"
                @click="clear_supplier_parts">
          {{ confirming ? '确认清空？' : '清除供应商料号' }}
        </button>
        <button v-if="confirming" class="btn btn-ghost !py-1.5 text-xs"
                :disabled="clearing" @click="confirming = false">取消</button>
      </div>
      <div class="flex max-h-56 flex-col gap-2 overflow-y-auto">
        <label v-for="comp in supplier_components" :key="comp.id"
               class="flex items-center gap-3 rounded-lg px-2 py-2 text-[12px]"
               style="background: var(--surface-2)">
          <input v-model="selected_ids" type="checkbox" :value="comp.id"
                 :disabled="clearing || mergeBusy" @change="confirming = false" />
          <span class="min-w-0 flex-1 truncate">{{ comp.name }}</span>
          <span class="mono">{{ comp.value }} {{ comp.package }}</span>
          <span>{{ comp.zone }}区/{{ comp.layer }}层/{{ comp.slot }}格</span>
          <span class="mono">{{ comp.supplier_part }}</span>
        </label>
        <span v-if="!supplier_components.length" class="text-xs"
              style="color: var(--text-dim)">没有供应商料号</span>
      </div>
      <div v-if="clear_note" class="mt-3 text-xs"
           style="color: var(--text-dim)">{{ clear_note }}</div>
    </section>
  </div>
</template>
