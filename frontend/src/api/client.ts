// 轻量 fetch 封装：统一 JSON、错误提取（含后端 409 {message, available} 语义）
import type {
  AdapterStatus, BackupSnapshot, BlockedSlot, BomLineOut, BomParseOut, BomPlan, ComponentItem, DataSummary, LayoutConfig,
  LookupCandidate, LookupResult, MergeResult, ReindexResult, ResetResult, RestoreResult, SearchIds, SwapOut,
  TransactionRow, UndoOut, UndoPeek,
} from './types'

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? ''
// 统一请求头：中文正文与 UTF-8
const JSON_HEADERS = { 'Content-Type': 'application/json; charset=utf-8' }

export class ApiError extends Error {
  status: number
  detail: unknown
  available?: number

  constructor(status: number, detail: unknown) {
    const msg = typeof detail === 'string'
      ? detail
      : detail && typeof detail === 'object' && 'message' in detail
        ? String((detail as { message: unknown }).message)
        : `请求失败（HTTP ${status}）`
    super(msg)
    this.status = status
    this.detail = detail
    if (detail && typeof detail === 'object' && 'available' in detail) {
      this.available = (detail as { available: number }).available
    }
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  // FormData 不能带 Content-Type（浏览器自动带 boundary）
  const isForm = init.body instanceof FormData
  const resp = await fetch(BASE + path, {
    ...init,
    headers: isForm ? { ...(init.headers ?? {}) }
      : { ...JSON_HEADERS, ...(init.headers ?? {}) },
  })
  if (resp.status === 204) return undefined as T
  const text = await resp.text()
  let body: unknown = null
  if (text) {
    try { body = JSON.parse(text) } catch { body = text }
  }
  if (!resp.ok) {
    const detail = (body as { detail?: unknown } | null)?.detail ?? body
    throw new ApiError(resp.status, detail)
  }
  return body as T
}

function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const sp = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') sp.set(k, String(v))
  }
  const s = sp.toString()
  return s ? `?${s}` : ''
}

export interface HealthInfo {
  status: string
  service: string
  version?: string
}

export const api = {
  health: () => request<HealthInfo>('/api/v1/health'),

  // 布局
  getLayout: () => request<LayoutConfig>('/api/v1/layout'),
  putLayout: (payload: Omit<LayoutConfig, 'updated_at' | 'blocked'>) =>
    request<LayoutConfig>('/api/v1/layout', { method: 'PUT', body: JSON.stringify(payload) }),

  // 元件
  listComponents: (opts: {
    q?: string; zone?: number; layer?: number; limit?: number; offset?: number
    match_case?: boolean; whole_word?: boolean; use_regex?: boolean
  } = {}) =>
    request<ComponentItem[]>('/api/v1/components' + qs(opts)),
  searchComponents: (opts: {
    q: string; match_case?: boolean; whole_word?: boolean; use_regex?: boolean
  }) => request<SearchIds>('/api/v1/components/search' + qs(opts)),
  createComponent: (payload: Record<string, unknown>) =>
    request<ComponentItem>('/api/v1/components', { method: 'POST', body: JSON.stringify(payload) }),
  patchComponent: (id: number, patch: Record<string, unknown>) =>
    request<ComponentItem>(`/api/v1/components/${id}`, { method: 'PATCH', body: JSON.stringify(patch) }),
  deleteComponent: (id: number) =>
    request<void>(`/api/v1/components/${id}`, { method: 'DELETE' }),
  // 多格存放：给元件加/减一个占用格
  addComponentSlot: (id: number, pos: { zone: number; layer: number; slot: number }) =>
    request<ComponentItem>(`/api/v1/components/${id}/slots`, {
      method: 'POST', body: JSON.stringify(pos),
    }),
  removeComponentSlot: (id: number, pos: { zone: number; layer: number; slot: number }) =>
    request<ComponentItem>(`/api/v1/components/${id}/slots` + qs({ ...pos }), { method: 'DELETE' }),

  // 合并「同名同值同封装」的重复元件（dryRun=1 只预览）
  mergeDuplicates: (dryRun = false) =>
    request<MergeResult>('/api/v1/system/merge-duplicates' + qs({ dry_run: dryRun ? 'true' : '' }), {
      method: 'POST',
    }),

  // 两个格子互换内容（位置与灯号对调）
  swapComponents: (aId: number, bId: number) =>
    request<SwapOut>('/api/v1/components/swap', {
      method: 'POST', body: JSON.stringify({ a_id: aId, b_id: bId }),
    }),
  changeStock: (id: number, delta: number, note?: string, source: 'ui' | 'guide' | 'system' = 'ui') =>
    request<ComponentItem>(`/api/v1/components/${id}/stock`, {
      method: 'POST',
      body: JSON.stringify({ delta, note: note ?? undefined, source }),
    }),

  // BOM（M3）
  importBomFile: (file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return request<BomParseOut>('/api/v1/bom/import', { method: 'POST', body: fd })
  },
  parseBom: (text: string) =>
    request<BomParseOut>('/api/v1/bom/parse', { method: 'POST', body: JSON.stringify({ text }) }),
  planBom: (text: string) =>
    request<BomPlan>('/api/v1/bom/plan', { method: 'POST', body: JSON.stringify({ text }) }),
  planBomRows: (lines: BomLineOut[]) =>
    request<BomPlan>('/api/v1/bom/plan-rows', {
      method: 'POST', body: JSON.stringify({ lines }),
    }),
  pickBom: (componentId: number, amount: number) =>
    request<ComponentItem>('/api/v1/bom/pick', {
      method: 'POST',
      body: JSON.stringify({ component_id: componentId, amount }),
    }),

  // 不可用格标记：返回标记后的完整列表
  blockSlot: (pos: { zone: number; layer: number; slot: number }) =>
    request<BlockedSlot[]>('/api/v1/layout/blocked', {
      method: 'POST', body: JSON.stringify(pos),
    }),
  unblockSlot: (pos: { zone: number; layer: number; slot: number }) =>
    request<BlockedSlot[]>('/api/v1/layout/blocked' + qs({ ...pos }), { method: 'DELETE' }),

  // 撤销上一步
  undoLast: () => request<UndoOut>('/api/v1/system/undo', { method: 'POST' }),
  peekUndo: () => request<UndoPeek>('/api/v1/system/undo'),

  // 单个候选的详情（点选候选时按编号补拉参数与数据手册）
  lookupDetail: (lcsc: string) =>
    request<LookupCandidate>('/api/v1/lookup/detail' + qs({ lcsc })),

  // 联网识别：任意输入 → 候选元件 + 可填表字段
  lookupAutofill: (text: string) =>
    request<LookupResult>('/api/v1/lookup/autofill', {
      method: 'POST', body: JSON.stringify({ text }),
    }),

  // 按 区→层→格 重排灯带序号（修老库里撞号的灯）
  reindexLeds: () => request<ReindexResult>('/api/v1/system/reindex-leds', { method: 'POST' }),

  // 数据概况：清空按钮据此禁用（没有可清内容时不给点）
  dataSummary: () => request<DataSummary>('/api/v1/system/data-summary'),

  setGuideLed: (componentId: number | null) =>
    request<{ ok: boolean }>('/api/v1/system/guide-led', {
      method: 'POST', body: JSON.stringify({ component_id: componentId }),
    }),

  // 一键清空：删光元件与流水，可选把布局恢复初始状态（后端先自动备份）
  resetData: (payload: { confirm: string; reset_layout: boolean }) =>
    request<ResetResult>('/api/v1/system/reset', {
      method: 'POST', body: JSON.stringify(payload),
    }),
  restoreData: (payload: { confirm: string; backup: BackupSnapshot }) =>
    request<RestoreResult>('/api/v1/system/restore', {
      method: 'POST', body: JSON.stringify(payload),
    }),

  // 审计 / 系统（M4）
  listTransactions: (limit = 30) =>
    request<TransactionRow[]>('/api/v1/transactions' + qs({ limit })),
  systemStatus: () => request<AdapterStatus>('/api/v1/system/status'),
}
