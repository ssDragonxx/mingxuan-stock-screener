import type { Evidence, FieldMeta, ScreenResult, StockResult } from './types'
import { condStatusText, fmtValue, stockStatusText } from './utils'

/** 单元格转义：含逗号、引号、换行时加引号，内部引号双写。 */
function csvCell(value: string | number | null | undefined): string {
  const text = value === null || value === undefined ? '' : String(value)
  if (/[",\n\r]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`
  }
  return text
}

function evidenceValue(item: Evidence, meta?: FieldMeta): string {
  const usableMeta = meta || ({ unit: item.unit } as unknown as FieldMeta)
  const value = fmtValue(item.value, item.field, usableMeta)
  const gap = item.gap_text ? `，${item.gap_text}` : ''
  return `${value}（${condStatusText(item.status)}${gap}）`
}

function conditionColumns(stocks: StockResult[]): { id: string; label: string }[] {
  const columns: { id: string; label: string }[] = []
  const seen = new Set<string>()
  for (const stock of stocks) {
    for (const condition of stock.conditions) {
      if (seen.has(condition.condition_id)) continue
      seen.add(condition.condition_id)
      columns.push({
        id: condition.condition_id,
        label: condition.group_label
          ? `${condition.group_label}·${condition.field_label}`
          : condition.field_label,
      })
    }
  }
  const counts = new Map<string, number>()
  return columns.map((column) => {
    const count = (counts.get(column.label) || 0) + 1
    counts.set(column.label, count)
    return { ...column, label: count > 1 ? `${column.label}(${count})` : column.label }
  })
}

/** 把一次筛选结果序列化为 CSV 文本（不含 BOM，由 downloadCsv 统一添加）。 */
export function buildResultCsv(
  result: ScreenResult,
  fieldMeta: Record<string, FieldMeta> = {},
): string {
  const stocks = result.stocks || []
  const columns = conditionColumns(stocks)
  const header = [
    '股票代码',
    '名称',
    '行业',
    '结论',
    '数据完整度',
    '失败项数',
    '缺失项数',
    '摘要理由',
    '风险提示',
    ...columns.map((column) => column.label),
  ]
  const lines = [header.map(csvCell).join(',')]
  for (const stock of stocks) {
    const evidenceById = new Map(stock.conditions.map((item) => [item.condition_id, item]))
    const row = [
      stock.thscode,
      stock.name,
      stock.industry,
      stockStatusText(stock.status),
      stock.data_completeness,
      stock.fail_count,
      stock.unknown_count,
      stock.summary_reason,
      (stock.risk_flags || []).join('；'),
      ...columns.map((column) => {
        const item = evidenceById.get(column.id)
        return item ? evidenceValue(item, fieldMeta[item.field]) : ''
      }),
    ]
    lines.push(row.map(csvCell).join(','))
  }
  return lines.join('\r\n')
}

/** 触发浏览器下载；UTF-8 BOM 保证 Excel 直接打开不乱码。 */
export function downloadCsv(filename: string, content: string): void {
  const blob = new Blob(['\ufeff' + content], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}
