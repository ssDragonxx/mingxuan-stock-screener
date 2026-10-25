import type { Evidence, FieldMeta } from './types'

export function opLabel(op?: string): string {
  return { '>=': '≥', '<=': '≤', '>': '>', '<': '<', '==': '=', '!=': '≠' }[op || ''] || op || ''
}

export function windowLabel(windowKey?: string): string {
  return (
    {
      latest_report: '最新报告期',
      current: '当前截面',
      last_20d: '近 20 日',
      last_60d: '近 60 日',
      last_120d: '近 120 日',
      ttm: '近 12 个月',
    }[windowKey || ''] || windowKey || '—'
  )
}

export function fmtValue(
  value: number | null | undefined,
  field: string,
  meta?: FieldMeta,
): string {
  if (value === null || value === undefined) return '—'
  const number = Number(value)
  if (!Number.isFinite(number)) return String(value)
  const unit = meta?.unit || ''
  const signed = Boolean(meta?.signed)
  if (unit === '%') {
    const text = `${number.toFixed(1)}%`
    return signed && number > 0 ? `+${text}` : text
  }
  if (unit === 'x') return `${number.toFixed(2)}x`
  if (unit === '次') return `${number.toFixed(2)}次`
  if (unit === '亿元') return `${number.toFixed(2)}亿元`
  if (unit === '元') return `${number.toFixed(2)}元`
  if (unit === '名') return `${Math.round(number)}名`
  return `${number.toFixed(1)}${unit}`
}

export function condStatusText(status?: string): string {
  return { pass: '通过', fail: '不通过', unknown: '未知' }[status || ''] || status || ''
}

export function stockStatusText(status?: string): string {
  return (
    { included: '入选', near_miss: '近邻', excluded: '未入选', unknown: '数据不足' }[status || ''] ||
    status ||
    ''
  )
}

export function statusIcon(status?: string): string {
  return { pass: '✓', fail: '×', unknown: '?' }[status || ''] || '·'
}

export function thresholdLabel(item: Evidence): string {
  if (item.field === 'pe_ttm' && item.op === '>' && Number(item.threshold) === 0) {
    return '有效 PE（剔除负值）'
  }
  return `${opLabel(item.op)} ${item.threshold}${item.unit || ''}`
}

export function sourceStatusLabel(status?: string): string {
  return (
    { ok: '正常', partial: '部分可用', missing: '缺失', degraded: '降级', failed: '失败' }[
      status || ''
    ] || status || '未知'
  )
}

export function formatCount(value?: number): string {
  if (value === undefined || value === null) return '—'
  return value.toLocaleString('zh-CN')
}

export function severityLabel(severity?: string): string {
  return (
    { hard: '硬冲突', soft: '可能过窄', semantic: '语义张力', data: '数据限制' }[severity || ''] ||
    '提示'
  )
}
