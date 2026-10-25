export type FieldMeta = {
  label: string
  unit: string
  step: number
  min?: number | null
  max?: number | null
  ops: string[]
  source: string
  frequency: string
  window: string
  desc: string
  signed?: boolean
  category?: string
  dataset?: string
}

export type Condition = {
  id: string
  field: string
  op: string
  value: number
  unit?: string
  window?: string
  confidence?: number
}

export type GroupOption = {
  id: string
  label: string
  conditions?: Condition[]
  replace_condition?: Condition
  set_value?: number
}

export type Group = {
  id: string
  label: string
  logic: string
  source_phrase?: string
  conditions: Condition[]
  options?: GroupOption[]
  definition?: string
}

export type DSL = {
  dsl_version: string
  universe: {
    type: string
    exclude_st?: boolean
    exclude_suspended?: boolean
    min_listed_days?: number
    exclude_bse?: boolean
  }
  groups: Group[]
  group_logic: string
  missing_policy: string
  ranking?: Record<string, unknown>
}

export type Assumption = {
  text: string
  confidence?: number
  alternatives?: string[]
}

export type Clarification = {
  id: string
  group_id: string
  question: string
  default: string
  options: GroupOption[]
}

export type Conflict = {
  severity: string
  code: string
  message: string
  suggestion?: string
}

export type Unsupported = {
  phrase: string
  reason: string
  alternatives?: string[]
}

export type DatasetStatus = {
  count?: number
  as_of?: string
  ready?: boolean
  report?: string
  coverage?: number
  note?: string
}

export type DataStatus = {
  mode: 'mock' | 'live'
  ready?: boolean
  universe?: { count: number; label: string }
  quote?: { as_of?: string; status?: string }
  valuation?: { as_of?: string; status?: string }
  daily_k?: { as_of?: string; status?: string }
  financials?: {
    latest_report?: string
    label?: string
    coverage?: number
    status?: string
    note?: string
  }
  datasets?: Record<string, DatasetStatus>
  sources?: { name: string; status: string; note?: string }[]
  definitions?: { key: string; label: string; text: string }[]
  hint?: string
  [key: string]: unknown
}

export type ParseResult = {
  query: string
  parser: string
  dsl: DSL
  field_meta: Record<string, FieldMeta>
  assumptions: Assumption[]
  clarifications: Clarification[]
  conflicts: Conflict[]
  unsupported: Unsupported[]
  meta?: Record<string, unknown>
  data_status?: DataStatus
}

export type Evidence = {
  condition_id: string
  group_id: string
  group_label: string
  field: string
  field_label: string
  value: number | null
  unit: string
  op: string
  threshold: number
  status: 'pass' | 'fail' | 'unknown'
  gap?: number | null
  gap_text?: string | null
  source: string
  as_of?: string | null
  note?: string | null
  category?: string
}

export type StockResult = {
  thscode: string
  name: string
  industry: string
  status: 'included' | 'near_miss' | 'excluded' | 'unknown'
  data_completeness: string
  summary_reason: string
  conditions: Evidence[]
  risk_flags: string[]
  raw: Record<string, unknown>
  fail_count: number
  unknown_count: number
  original_unknown_count: number
  min_gap: number
}

export type Summary = {
  universe: number
  cheap_excluded: number
  after_cheap: number
  evaluated: number
  truncated: number
  included: number
  near_miss: number
  excluded: number
  unknown: number
  pending: number
  data_completeness: string
  financial_report?: string
}

export type FunnelStep = {
  label: string
  count: number
}

export type SensitivityItem = {
  condition_id: string
  label: string
  field: string
  unit: string
  current: number
  points: { threshold: number; included: number }[]
  binding: boolean
  relax_to: number | null
  delta: number
  direction: string
}

export type BreakdownItem = {
  field: string
  label: string
  count: number
  kind: string
}

export type ScreenResult = {
  summary: Summary
  funnel: FunnelStep[]
  stocks: StockResult[]
  excluded_breakdown: BreakdownItem[]
  sensitivity: SensitivityItem[]
  data_status: DataStatus
  warnings: string[]
  meta: Record<string, unknown>
}

export type PreviewResult = {
  summary: Summary
  funnel: FunnelStep[]
  warnings: string[]
  data_status: DataStatus
  meta: Record<string, unknown>
}

export type Job = {
  job_id: string
  status: 'queued' | 'running' | 'done' | 'failed'
  progress: { stage: string; done: number; total: number; message: string }
  result?: ScreenResult | null
  error?: { code: string; message: string; hint?: string } | null
}

export type Strategy = {
  id: string
  name: string
  query?: string
  created_at: string
  monitor_enabled: number
  last_run_at?: string
}

export type Explanation = {
  text: string
  mode: 'llm' | 'template'
  number_check?: string
  fallback_reason?: string
  sections?: { title: string; text: string }[]
  facts_used?: { indicators: number; periods: number; conditions: number }
}

export type Toast = {
  id: number
  message: string
}
