<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Download, ShoppingCart } from '@lucide/vue'
import { api } from '../api/client'
import type { BomProject, Replenishment } from '../api/types'
import { csv_content, download_file } from '../utils/download'

const projects = ref<BomProject[]>([])
const selected = ref<number[]>([])
const include_thresholds = ref(true)
const result = ref<Replenishment | null>(null)
const busy = ref(false)
const error = ref('')

/** 按当前库存重新汇总所选项目与补货阈值。 */
async function generate() {
  busy.value = true
  error.value = ''
  result.value = null
  try { result.value = await api.replenish(selected.value, include_thresholds.value) }
  catch (e) { error.value = e instanceof Error ? e.message : String(e) }
  finally { busy.value = false }
}

/** 导出已核对的采购清单，包含尚未建档的物料。 */
function export_list() {
  if (!result.value) return
  const rows: (string | number)[][] = [[
    '名称', '标称值', '封装', '厂商料号', '供应商料号',
    '现有', '项目需求', '补货阈值', '采购数量', '状态',
  ], ...result.value.items.map(item => [
    item.name, item.value, item.package, item.manufacturer_part,
    item.supplier_part, item.available, item.demand, item.threshold,
    item.purchase, item.unresolved ? '未匹配库存' : '已匹配',
  ])]
  download_file('chipnest-补货清单.csv', csv_content(rows), 'text/csv;charset=utf-8')
}

onMounted(async () => {
  try {
    projects.value = (await api.listProjects()).filter(project =>
      !project.plan.complete || project.cursor < project.plan.steps.length)
    await generate()
  } catch (e) { error.value = e instanceof Error ? e.message : String(e) }
})
</script>

<template>
  <section class="flex min-h-0 flex-col gap-3 rounded-2xl p-4"
           style="background: var(--panel); border: 1px solid var(--line)">
    <div class="flex items-center gap-2 text-sm font-extrabold">
      <ShoppingCart :size="16" style="color: var(--accent-strong)" /> 补货清单
      <button class="btn ml-auto !py-1.5 text-xs" :disabled="busy"
              @click="generate">汇总需求</button>
    </div>
    <label class="flex items-center gap-2 text-xs">
      <input v-model="include_thresholds" type="checkbox" :disabled="busy"
             @change="result = null" />补货阈值
    </label>
    <details v-if="projects.length" class="rounded-xl p-3"
             style="background: var(--surface-2)">
      <summary class="cursor-pointer text-xs font-bold">BOM 项目 · 已选 {{ selected.length }}</summary>
      <div class="mt-3 flex max-h-36 flex-col gap-2 overflow-auto">
        <label v-for="project in projects" :key="project.id"
               class="flex items-center gap-2 text-xs">
          <input v-model="selected" type="checkbox" :value="project.id"
                 :disabled="busy" @change="result = null" />
          <span>{{ project.name }}</span><span class="chip ml-auto">{{ project.copies }} 份</span>
        </label>
      </div>
    </details>
    <div v-if="error" class="text-xs" style="color: var(--danger)">{{ error }}</div>
    <template v-if="result">
      <div class="flex gap-2">
        <span class="chip">{{ result.items.length }} 项</span>
        <span v-if="result.pending_choices" class="chip" style="color: var(--warn)">
          待确认 {{ result.pending_choices }} 项
        </span>
      </div>
      <div class="max-h-[44vh] overflow-auto rounded-xl"
           style="border: 1px solid var(--line)">
        <table class="w-full text-left text-xs">
          <thead class="sticky top-0" style="background: var(--surface-2)">
            <tr><th class="p-3">元件 / 料号</th><th class="p-3 text-right">现有</th>
              <th class="p-3 text-right">需求</th><th class="p-3 text-right">阈值</th>
              <th class="p-3 text-right">采购</th></tr>
          </thead>
          <tbody>
            <tr v-for="(item, index) in result.items" :key="index"
                style="border-top: 1px solid var(--line)">
              <td class="p-3"><div class="font-bold">{{ item.name }}
                <span class="mono font-normal">{{ item.value }} {{ item.package }}</span></div>
                <div class="mono mt-1" style="color: var(--text-faint)">
                  {{ item.manufacturer_part || item.supplier_part }}
                  <span v-if="item.unresolved" style="color: var(--warn)">未匹配库存</span>
                </div>
              </td>
              <td class="num p-3 text-right">{{ item.available }}</td>
              <td class="num p-3 text-right">{{ item.demand }}</td>
              <td class="num p-3 text-right">{{ item.threshold }}</td>
              <td class="num p-3 text-right font-bold" style="color: var(--accent-ink)">
                {{ item.purchase }}
              </td>
            </tr>
          </tbody>
        </table>
        <div v-if="!result.items.length" class="p-5 text-center text-xs">没有需要补货的元件</div>
      </div>
      <button class="btn self-end" :disabled="!result.items.length || busy" @click="export_list">
        <Download :size="14" /> 导出 CSV
      </button>
    </template>
  </section>
</template>
