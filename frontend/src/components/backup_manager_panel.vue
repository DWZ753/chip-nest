<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { Download, FileUp, FolderOpen, RefreshCw, Trash2 } from '@lucide/vue'
import { api } from '../api/client'
import type { BackupFile, BackupSettings, BackupSnapshot } from '../api/types'
import { download_file } from '../utils/download'

const emit = defineEmits<{ reset: []; refresh: []; busy: [boolean] }>()
const option = ref<BackupSettings | null>(null)
const files = ref<BackupFile[]>([])
const busy = ref(false)
const message = ref('')
const error = ref('')
const selected_backup = ref<BackupSnapshot | null>(null)
const selected_name = ref('')
const confirm_text = ref('')
const deleting = ref('')
const desktop = window.chipnest
const reasons: Record<string, string> = {
  manual: '手动', auto: '自动', reset: '清空前', restore: '恢复前',
}
watch(busy, value => emit('busy', value))

/** 同时读取策略和当前目录的备份历史。 */
async function load() {
  busy.value = true
  error.value = ''
  try {
    const [settings, history] = await Promise.all([
      api.backupSettings(), api.listBackups(),
    ])
    option.value = settings
    files.value = history
  } catch (e) { error.value = e instanceof Error ? e.message : String(e) }
  finally { busy.value = false }
}

/** 保存备份策略，历史随所选目录刷新。 */
async function save() {
  if (!option.value || busy.value) return
  busy.value = true
  error.value = ''
  try {
    option.value = await api.saveBackupSettings(option.value)
    files.value = await api.listBackups()
    message.value = '已更新备份策略'
    emit('refresh')
  } catch (e) { error.value = e instanceof Error ? e.message : String(e) }
  finally { busy.value = false }
}

/** 桌面端使用原生目录选择器，浏览器可填写完整路径。 */
async function choose_directory() {
  if (!desktop || !option.value) return
  const path = await desktop.chooseBackupDirectory()
  if (path) option.value.directory = path
}

/** 创建手动快照；历史可以稍后再次下载。 */
async function create() {
  busy.value = true
  error.value = ''
  try {
    const result = await api.createBackup()
    files.value = await api.listBackups()
    option.value = await api.backupSettings()
    message.value = `已备份 ${result.backup.components.length} 个元件、${result.backup.projects?.length ?? 0} 个项目`
    emit('refresh')
  } catch (e) { error.value = e instanceof Error ? e.message : String(e) }
  finally { busy.value = false }
}

/** 从历史读取并下载完整 JSON。 */
async function download(file: BackupFile) {
  busy.value = true
  error.value = ''
  try {
    const snapshot = await api.getBackup(file.name)
    download_file(file.name, JSON.stringify(snapshot, null, 2),
      'application/json;charset=utf-8')
  } catch (e) { error.value = e instanceof Error ? e.message : String(e) }
  finally { busy.value = false }
}

/** 删除单份历史备份，第二次点击同一文件才执行。 */
async function remove(file: BackupFile) {
  if (deleting.value !== file.name) { deleting.value = file.name; return }
  busy.value = true
  error.value = ''
  try {
    await api.deleteBackup(file.name)
    files.value = await api.listBackups()
    message.value = '已删除备份'
    emit('refresh')
  } catch (e) { error.value = e instanceof Error ? e.message : String(e) }
  finally { busy.value = false; deleting.value = '' }
}

/** 选择历史快照，恢复仍需要输入确认词。 */
async function select_history(file: BackupFile) {
  busy.value = true
  error.value = ''
  try {
    selected_backup.value = await api.getBackup(file.name)
    selected_name.value = file.name
    confirm_text.value = ''
  } catch (e) { error.value = e instanceof Error ? e.message : String(e) }
  finally { busy.value = false }
}

/** 导入外部备份的基本验证，完整验证由恢复接口完成。 */
async function select_file(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  selected_backup.value = null
  error.value = ''
  try {
    const data = JSON.parse(await file.text())
    if (data.app !== 'ChipNest' || !Array.isArray(data.components)
        || !Array.isArray(data.transactions)) throw new Error('备份文件无效')
    selected_backup.value = data as BackupSnapshot
    selected_name.value = file.name
    confirm_text.value = ''
  } catch { error.value = '备份文件无效' }
}

/** 覆盖前备份与恢复由后端同一请求处理。 */
async function restore() {
  if (!selected_backup.value || confirm_text.value !== '恢复' || busy.value) return
  busy.value = true
  error.value = ''
  try {
    const result = await api.restoreData({
      confirm: confirm_text.value, backup: selected_backup.value,
    })
    message.value = `已恢复 ${result.components} 个元件`
    selected_backup.value = null
    files.value = await api.listBackups()
    emit('reset')
  } catch (e) { error.value = e instanceof Error ? e.message : String(e) }
  finally { busy.value = false }
}
onMounted(load)
</script>

<template>
  <div class="flex min-h-0 flex-col gap-3 overflow-y-auto pr-1">
    <section v-if="option" class="rounded-2xl p-4"
             style="background: var(--panel); border: 1px solid var(--line)">
      <div class="flex items-center justify-between">
        <h3 class="text-sm font-extrabold">自动备份</h3>
        <label class="flex items-center gap-2 text-xs">
          <input v-model="option.enabled" type="checkbox" :disabled="busy" />启用
        </label>
      </div>
      <div class="mt-3 grid grid-cols-2 gap-3">
        <label class="text-xs">间隔小时
          <input v-model.number="option.interval_hours" class="input num mt-1.5"
                 type="number" min="1" max="720" :disabled="busy" />
        </label>
        <label class="text-xs">自动备份保留份数
          <input v-model.number="option.keep_count" class="input num mt-1.5"
                 type="number" min="1" max="100" :disabled="busy" />
        </label>
      </div>
      <label class="mt-3 block text-xs">备份目录</label>
      <div class="mt-1.5 flex gap-2">
        <input v-model="option.directory" class="input min-w-0 flex-1 text-xs"
               :placeholder="option.resolved_directory" aria-label="备份目录"
               :disabled="busy" />
        <button v-if="desktop" class="btn !px-3" title="选择备份目录"
                :disabled="busy" @click="choose_directory"><FolderOpen :size="15" /></button>
        <button class="btn btn-ghost !px-3 text-xs" :disabled="busy"
                @click="option.directory = ''">默认目录</button>
      </div>
      <div class="mt-3 flex flex-wrap items-center gap-2">
        <span v-if="option.last_backup_at" class="text-[11px]" style="color: var(--text-faint)">
          最近备份 {{ new Date(option.last_backup_at + 'Z').toLocaleString() }}
        </span>
        <button class="btn ml-auto !py-1.5 text-xs" :disabled="busy" @click="save">保存策略</button>
      </div>
      <div v-if="option.last_error" class="mt-2 text-xs" style="color: var(--danger)">
        {{ option.last_error }}
      </div>
    </section>
    <section class="rounded-2xl p-4"
             style="background: var(--panel); border: 1px solid var(--line)">
      <div class="flex items-center gap-2">
        <h3 class="text-sm font-extrabold">备份历史</h3>
        <button class="icon-btn ml-auto" title="刷新备份" :disabled="busy" @click="load">
          <RefreshCw :size="14" />
        </button>
        <button class="btn !py-1.5 text-xs" :disabled="busy" @click="create">创建备份</button>
      </div>
      <div class="mt-3 flex max-h-56 flex-col gap-2 overflow-auto">
        <div v-for="file in files" :key="file.name" class="rounded-xl p-3"
             style="background: var(--surface-2)">
          <div class="flex flex-wrap items-center gap-2 text-xs">
            <span class="chip">{{ reasons[file.reason] ?? file.reason }}</span>
            <span>{{ file.exported_at.replace('T', ' ') }}</span>
            <span class="ml-auto num" style="color: var(--text-faint)">
              {{ file.components }} 元件 · {{ file.projects }} 项目 · {{ Math.ceil(file.size / 1024) }} KB
            </span>
          </div>
          <div class="mt-2 flex items-center gap-2">
            <span class="mono min-w-0 flex-1 truncate text-[10px]" :title="file.name"
                  style="color: var(--text-faint)">{{ file.name }}</span>
            <button class="icon-btn" title="下载备份" :disabled="busy" @click="download(file)">
              <Download :size="14" /></button>
            <button class="btn !px-2 !py-1 text-xs" :disabled="busy" @click="select_history(file)">恢复</button>
            <button class="btn btn-ghost !px-2 !py-1 text-xs" :disabled="busy" @click="remove(file)">
              <Trash2 :size="13" />{{ deleting === file.name ? '确认删除' : '删除' }}</button>
            <button v-if="deleting === file.name" class="btn btn-ghost !px-2 !py-1 text-xs"
                    :disabled="busy" @click="deleting = ''">取消</button>
          </div>
        </div>
        <div v-if="!files.length" class="py-4 text-center text-xs" style="color: var(--text-faint)">暂无备份</div>
      </div>
      <label class="btn mt-3 inline-flex cursor-pointer !py-1.5 text-xs"
             :class="{ 'pointer-events-none opacity-50': busy }">
        <FileUp :size="14" />选择 JSON 备份
        <input type="file" accept=".json" class="hidden" :disabled="busy" @change="select_file" />
      </label>
    </section>
    <section v-if="selected_backup" class="rounded-2xl p-4"
             style="background: var(--panel); border: 1px solid var(--danger)">
      <h3 class="text-sm font-bold" style="color: var(--danger)">将覆盖当前数据</h3>
      <div class="mt-2 break-all text-xs">{{ selected_name }}</div>
      <div class="mt-1 text-xs" style="color: var(--text-dim)">
        {{ selected_backup.components.length }} 元件 · {{ selected_backup.projects?.length ?? 0 }} 项目
      </div>
      <label class="mt-3 block text-xs">确认词</label>
      <input v-model="confirm_text" class="input mt-1.5" placeholder="恢复"
             maxlength="4" :disabled="busy" @keyup.enter="restore" />
      <div class="mt-3 flex gap-2">
        <button class="btn btn-danger" :disabled="busy || confirm_text !== '恢复'"
                @click="restore">确认恢复</button>
        <button class="btn btn-ghost" :disabled="busy"
                @click="selected_backup = null">取消</button>
      </div>
    </section>
    <div v-if="message" class="text-xs" style="color: var(--success)">{{ message }}</div>
    <div v-if="error" class="text-xs" style="color: var(--danger)">{{ error }}</div>
  </div>
</template>
