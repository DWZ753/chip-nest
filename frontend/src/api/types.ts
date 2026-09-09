// 与后端 schema.py 对齐的出入参类型（M3/M4 契约，勿单方面改名）
export interface LayoutConfig {
  zone_count: number
  layer_count: number
  row_count: number
  col_count: number
  zone_names: string[]
  updated_at: string
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
  requested: number
  complete: boolean
}

export type AdapterMode = 'serial' | 'mock'

export interface AdapterStatus {
  mode: AdapterMode
  connected: boolean
  device: string | null
  error: string | null
}

// WS /api/v1/ws/status 消息：{"type":"adapter.status", ...AdapterStatus}
export interface WsStatusMessage extends AdapterStatus {
  type: string
}