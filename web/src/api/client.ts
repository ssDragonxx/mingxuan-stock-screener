import type {
  DataStatus,
  DSL,
  Explanation,
  Job,
  ParseResult,
  PreviewResult,
  StockResult,
  Strategy,
} from '../types'

export class ApiError extends Error {
  status: number
  payload: unknown

  constructor(message: string, status: number, payload: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.payload = payload
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  const text = await response.text()
  let data: any = null
  try {
    data = text ? JSON.parse(text) : null
  } catch {
    data = null
  }
  if (!response.ok) {
    const message =
      data?.error?.message ||
      data?.detail?.message ||
      (typeof data?.detail === 'string' ? data.detail : null) ||
      `请求失败（${response.status}）`
    throw new ApiError(message, response.status, data)
  }
  return data as T
}

export function getStatus(): Promise<DataStatus> {
  return request<DataStatus>('/api/status')
}

export function parseIntent(query: string, universe: string): Promise<ParseResult> {
  return request<ParseResult>('/api/parse', {
    method: 'POST',
    body: JSON.stringify({ query, universe }),
  })
}

export function preview(dsl: DSL): Promise<PreviewResult> {
  return request<PreviewResult>('/api/preview', {
    method: 'POST',
    body: JSON.stringify({ dsl }),
  })
}

export function createScreenJob(dsl: DSL): Promise<{ job_id: string }> {
  return request<{ job_id: string }>('/api/screen/jobs', {
    method: 'POST',
    body: JSON.stringify({ dsl }),
  })
}

export function getJob(jobId: string): Promise<Job> {
  return request<Job>(`/api/screen/jobs/${jobId}`)
}

export function diagnose(query: string, dsl: DSL): Promise<{ stock: StockResult }> {
  return request<{ stock: StockResult }>('/api/diagnose', {
    method: 'POST',
    body: JSON.stringify({ query, dsl }),
  })
}

export function explain(query: string, dsl: DSL): Promise<{ stock: StockResult; explanation: Explanation }> {
  return request<{ stock: StockResult; explanation: Explanation }>('/api/explain', {
    method: 'POST',
    body: JSON.stringify({ query, dsl }),
  })
}

export function listStrategies(): Promise<{ items: Strategy[] }> {
  return request<{ items: Strategy[] }>('/api/strategies')
}

export function createStrategy(payload: {
  name: string
  query?: string
  dsl: DSL
  monitor_enabled: boolean
}): Promise<{ id: string; monitor_enabled: boolean }> {
  return request<{ id: string; monitor_enabled: boolean }>('/api/strategies', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function runStrategy(id: string): Promise<any> {
  return request<any>(`/api/strategies/${id}/run`, { method: 'POST' })
}

export function getStrategyRuns(id: string): Promise<{ items: any[] }> {
  return request<{ items: any[] }>(`/api/strategies/${id}/runs`)
}
