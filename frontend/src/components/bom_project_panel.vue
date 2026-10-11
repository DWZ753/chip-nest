<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Copy, FolderOpen, Save, Trash2 } from '@lucide/vue'
import { api } from '../api/client'
import type { BomLineOut, BomPlan, BomProject } from '../api/types'

const props = defineProps<{
  lines: BomLineOut[] | null
  selections: Record<number, number>
  fileName: string
  disabled: boolean
}>()
const emit = defineEmits<{
  load: [BomProject]; reset: []; copies: [number];
  project: [BomProject | null]; plan: [BomPlan]; busy: [boolean]
}>()
const projects = ref<BomProject[]>([])
const current = ref<BomProject | null>(null)
const name = ref('')
const copies = ref(1)
const working = ref(false)
const error = ref('')
const message = ref('')
const deleting = ref<number | null>(null)
const in_progress = computed(() => !!current.value?.cursor)

/** 切换或新建项目，原有项目的库存操作不会被重复执行。 */
function reset() {
  current.value = null
  name.value = ''
  copies.value = 1
  message.value = ''
  emit('project', null)
  emit('copies', 1)
  emit('reset')
}

/** 打开时读取最新进度，保存的清单和匹配回填到取料工作区。 */
async function open(project: BomProject, copy = false) {
  if (props.disabled || working.value) return
  working.value = true
  emit('busy', true)
  error.value = ''
  try {
    const loaded = await api.getProject(project.id)
    current.value = copy ? null : loaded
    name.value = loaded.name + (copy ? ' 副本' : '')
    copies.value = loaded.copies
    emit('project', current.value)
    emit('copies', loaded.copies)
    emit('load', { ...loaded, cursor: copy ? 0 : loaded.cursor })
    message.value = copy ? '已创建制作副本' : '已打开项目'
  } catch (e) { error.value = e instanceof Error ? e.message : String(e) }
  finally { working.value = false; emit('busy', false) }
}

/** 保存项目；开始引导前重新校验当前库存和匹配。 */
async function save(): Promise<BomProject | null> {
  if (!props.lines?.length || working.value) return null
  working.value = true
  emit('busy', true)
  error.value = ''
  try {
    const saved = await api.saveProject({
        name: name.value.trim() || props.fileName || 'BOM 项目',
        lines: props.lines, selections: props.selections,
        copies: copies.value, revision: current.value?.revision,
      }, current.value?.id)
    current.value = saved
    name.value = saved.name
    projects.value = await api.listProjects()
    emit('project', saved)
    emit('plan', saved.plan)
    message.value = '已保存项目'
    return saved
  } catch (e) { error.value = e instanceof Error ? e.message : String(e) }
  finally { working.value = false; emit('busy', false) }
  return null
}

/** 删除项目前二次确认，当前工作区同步清空。 */
async function remove(project: BomProject) {
  if (deleting.value !== project.id) { deleting.value = project.id; return }
  working.value = true
  emit('busy', true)
  error.value = ''
  try {
    await api.deleteProject(project.id)
    if (current.value?.id === project.id) reset()
    projects.value = await api.listProjects()
    message.value = '已删除项目'
  } catch (e) { error.value = e instanceof Error ? e.message : String(e) }
  finally { working.value = false; deleting.value = null; emit('busy', false) }
}

/** 完成或未完成状态只来自保存的取料进度。 */
function status(project: BomProject): string {
  if (!project.plan.complete) return project.cursor ? '待补料' : '待规划'
  if (project.cursor >= project.plan.steps.length) return '已完成'
  return project.cursor ? '取料中' : '待取料'
}

onMounted(async () => {
  try { projects.value = await api.listProjects() }
  catch (e) { error.value = e instanceof Error ? e.message : String(e) }
})
defineExpose({ prepare_start: save, reset })
</script>

<template>
  <section class="rounded-xl p-3" style="background: var(--panel); border: 1px solid var(--line)">
    <div class="flex flex-wrap items-end gap-2">
      <label class="min-w-0 flex-1 text-[11px]">项目名称
        <input v-model="name" class="input mt-1 !py-1.5 text-xs" maxlength="80"
               :placeholder="fileName || 'BOM 项目'"
               :disabled="disabled || working || in_progress" />
      </label>
      <label class="w-20 text-[11px]">制作份数
        <input v-model.number="copies" class="input num mt-1 !py-1.5 text-xs"
               type="number" min="1" max="10000"
               :disabled="disabled || working || in_progress"
               @input="emit('copies', copies)" />
      </label>
      <button class="btn !px-3 !py-1.5 text-xs"
              :disabled="disabled || working || !lines?.length
                || !Number.isInteger(copies) || copies < 1 || copies > 10000"
              @click="save"><Save :size="13" />保存</button>
      <button class="btn btn-ghost !px-3 !py-1.5 text-xs"
              :disabled="disabled || working" @click="reset">新建</button>
    </div>
    <div v-if="current" class="mt-2 flex gap-2">
      <span class="chip">{{ status(current) }}</span>
      <span class="chip num">{{ current.cursor }} / {{ current.plan.steps.length }} 步</span>
    </div>
    <details v-if="projects.length" class="mt-3 text-xs">
      <summary class="cursor-pointer font-bold">已保存项目 · {{ projects.length }}</summary>
      <div class="mt-2 flex max-h-40 flex-col gap-2 overflow-auto">
        <div v-for="project in projects" :key="project.id" class="flex flex-wrap items-center gap-2 rounded-lg p-2"
             style="background: var(--surface-2)">
          <span class="min-w-0 flex-1 truncate font-bold">{{ project.name }}</span>
          <span class="chip">{{ status(project) }} · {{ project.copies }} 份</span>
          <button class="icon-btn" title="打开项目" :disabled="disabled || working" @click="open(project)">
            <FolderOpen :size="14" /></button>
          <button class="icon-btn" title="新建制作副本" :disabled="disabled || working" @click="open(project, true)">
            <Copy :size="14" /></button>
          <button class="btn btn-ghost !px-2 !py-1 text-xs" title="删除项目"
                  :disabled="disabled || working" @click="remove(project)">
            <Trash2 :size="13" />{{ deleting === project.id ? '确认删除' : '' }}</button>
          <button v-if="deleting === project.id" class="btn btn-ghost !px-2 !py-1 text-xs"
                  @click="deleting = null">取消</button>
        </div>
      </div>
    </details>
    <div v-if="message" class="mt-2 text-xs" style="color: var(--success)">{{ message }}</div>
    <div v-if="error" class="mt-2 text-xs" style="color: var(--danger)">{{ error }}</div>
  </section>
</template>
