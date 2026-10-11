// 与后端 schema.py 对齐的出入参类型（M3/M4 契约，勿单方面改名）
export interface LayoutConfig {
  zone_count: number
  layer_count: number
  row_count: number
  col_count: number
  zone_names: string[]
  zone_sizes: number[][]
  zone_layers: number[]
  blocked: BlockedSlot[]
  updated_at: string
}

// 被标记为不可用的格子（物理容器坏了等）
export interface BlockedSlot {
  zone: number
  layer: number
  slot: number
}

export interface ComponentItem {
  id: number
  name: string
  value: string | null
  package: string | null
  quantity: number
  threshold: number
  zone: number
  layer: number
  slot: number
  led_index: number | null
  manufacturer_part: string | null
  supplier_part: string | null
  tags: string[]
  display_tags: string[]
  display_fields: string[]
  card_items: string[]
  slots: SlotRef[]
  slot_count: number
}

export interface SearchIds {
  ids: number[]
}

// 一个元件的附加占用格（主格是 zone/layer/slot）
export interface SlotRef {
  zone: number
  layer: number
  slot: number
}

export interface MergeGroup {
  name: string
  value: string
  package: string
  keep_id: number
  member_ids: number[]
  total_quantity: number
  moved_slots: number
  members: ComponentItem[]
  differences: string[]
  conflicting: boolean
  fingerprint: string
}

export interface MergeResult {
  dry_run: boolean
  groups: MergeGroup[]
  merged_groups: number
  merged_components: number
  skipped_groups: number
}

export interface TransactionRow {
  id: number
  ts: string
  kind: string
  component_id: number | null
  delta: number
  detail: string | null
  source: string | null
}

export interface BomLineOut {
  raw: string
  name: string
  value: string | null
  package: string | null
  quantity: number
  manufacturer_part?: string | null
  supplier_part?: string | null
}

export interface BomParseOut {
  lines: BomLineOut[]
  total_quantity: number
}

export interface BomStep {
  component: ComponentItem
  quantity: number
  line_indexes: number[]
}

export interface BomMissing {
  reason: 'not_found' | 'shortage'
  raw: string
  name: string
  value: string | null
  package: string | null
  quantity: number
  component_id: number | null
  available: number | null
}

export interface BomPlan {
  steps: BomStep[]
  missing: BomMissing[]
  choices: BomChoice[]
  requested: number
  complete: boolean
}

export interface BomChoice {
  line_index: number
  line: BomLineOut
  candidates: { component: ComponentItem; reasons: string[] }[]
}

export type AdapterMode = 'serial' | 'mock'

export interface AdapterStatus {
  mode: AdapterMode
  connected: boolean
  device: string | null
  error: string | null
}

// 两个格子互换内容
export interface SwapOut {
  a: ComponentItem
  b: ComponentItem
}

// 撤销
export interface UndoOut {
  ok: boolean
  label: string
  message: string
  component_ids: number[]
}

export interface UndoPeek {
  label: string
  ts: string | null
}

// 灯带序号重排结果
export interface ReindexResult {
  total: number
  changed: number
}

// 数据概况（清空按钮据此禁用）
export interface DataSummary {
  components: number
  transactions: number
  projects: number
  empty: boolean
}

// 一键清空（POST /api/v1/system/reset）的返回
export interface ResetResult {
  deleted_components: number
  deleted_transactions: number
  deleted_projects: number
  backup_path: string
  layout_reset: boolean
}

export interface BackupSnapshot {
  app: 'ChipNest'
  reason: string
  exported_at: string
  layout: Omit<LayoutConfig, 'blocked' | 'updated_at'> | null
  components: ComponentItem[]
  transactions: TransactionRow[]
  blocked_slots: BlockedSlot[]
  projects?: BomProject[]
}

export interface RestoreResult {
  components: number
  transactions: number
  blocked_slots: number
  projects: number
  backup_path: string
}

export interface BackupResult {
  backup_path: string
  backup: BackupSnapshot
}

export interface BackupSettings {
  enabled: boolean
  interval_hours: number
  keep_count: number
  directory: string
  resolved_directory: string
  last_backup_at: string | null
  last_error: string
}

export interface BackupFile {
  name: string
  exported_at: string
  reason: string
  size: number
  components: number
  projects: number
}

export interface BomProject {
  id: number
  name: string
  lines: BomLineOut[]
  selections: Record<number, number>
  copies: number
  plan: BomPlan
  cursor: number
  revision: number
  created_at: string
  updated_at: string
}

export interface ProjectSave {
  name: string
  lines: BomLineOut[]
  selections: Record<number, number>
  copies: number
  revision?: number
}

export interface StocktakeEntry {
  component_id: number
  expected_quantity: number
  quantity: number
}

export interface ReplenishmentItem {
  component_id: number | null
  name: string
  value: string
  package: string
  manufacturer_part: string
  supplier_part: string
  available: number
  threshold: number
  demand: number
  purchase: number
  unresolved: boolean
}

export interface Replenishment {
  items: ReplenishmentItem[]
  pending_choices: number
}

// 联网识别候选（后端 /api/v1/lookup/*）
export interface LookupCandidate {
  lcsc: string
  mpn: string
  name: string
  value: string
  package: string
  manufacturer: string
  category: string
  description: string
  stock: number
  price: number | null
  datasheet: string
  source: string
  params: Record<string, string>
}

export interface LookupResult {
  query: string
  kind: 'lcsc' | 'keyword'
  best: LookupCandidate | null
  candidates: LookupCandidate[]
  fields: Record<string, string>
  online: boolean
}

// WS /api/v1/ws/status 消息：{"type":"adapter.status", ...AdapterStatus}
export interface WsStatusMessage extends AdapterStatus {
  type: string
}
