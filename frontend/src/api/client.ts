// 轻量 fetch 封装：统一 JSON、错误提取（含后端 409 {message, available} 语义）
import type {
  AdapterStatus, BomParseOut, BomPlan, ComponentItem, LayoutConfig,
  TransactionRow,
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

function qs(params: Record<string, string | number | null | undefined>): string {
  const sp = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') sp.set(k, String(v))
  }
  const s = sp.toString()
  return s ? `?${s}` : ''
}

export const api = {
  // 布局
  getLayout: () => request<LayoutConfig>('/api/v1/layout'),
  putLayout: (payload: Omit<LayoutConfig, 'updated_at'>) =>
    request<LayoutConfig>('/api/v1/layout', { method: 'PUT', body: JSON.stringify(payload) }),

  // 元件
  listComponents: (opts: { q?: string; zone?: number; layer?: number; limit?: number } = {}) =>
    request<ComponentItem[]>('/api/v1/components' + qs(opts)),
  createComponent: (payload: Record<string, unknown>) =>
    request<ComponentItem>('/api/v1/components', { method: 'POST', body: JSON.stringify(payload) }),
  patchComponent: (id: number, patch: Record<string, unknown>) =>
    request<ComponentItem>(`/api/v1/components/${id}`, { method: 'PATCH', body: JSON.stringify(patch) }),
  deleteComponent: (id: number) =>
    request<void>(`/api/v1/components/${id}`, { method: 'DELETE' }),
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
  pickBom: (componentId: number, amount: number) =>
    request<ComponentItem>('/api/v1/bom/pick', {
      method: 'POST',
      body: JSON.stringify({ component_id: componentId, amount }),
    }),

  // 审计 / 系统（M4）
  listTransactions: (limit = 30) =>
    request<TransactionRow[]>('/api/v1/transactions' + qs({ limit })),
  systemStatus: () => request<AdapterStatus>('/api/v1/system/status'),
}