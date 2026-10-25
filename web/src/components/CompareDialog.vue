<script setup lang="ts">
import { computed } from 'vue'
import { useScreeningStore } from '../stores/screening'
import { condStatusText, fmtValue, stockStatusText } from '../utils'
import type { Evidence, StockResult } from '../types'

const store = useScreeningStore()
const stocks = computed(() => store.compareStocks)

const rows = computed(() => {
  const map = new Map<
    string,
    { group: string; label: string; field: string; values: Record<string, Evidence> }
  >()
  for (const stock of stocks.value) {
    for (const item of stock.conditions) {
      const key = `${item.group_label}||${item.field_label}`
      if (!map.has(key)) {
        map.set(key, {
          group: item.group_label,
          label: item.field_label,
          field: item.field,
          values: {},
        })
      }
      map.get(key)!.values[stock.thscode] = item
    }
  }
  return Array.from(map.values())
})

function valueFor(item?: Evidence): string {
  if (!item) return '—'
  return fmtValue(item.value, item.field, store.parseResult?.field_meta?.[item.field])
}

function close() {
  store.showCompare = false
}

function remove(stock: StockResult) {
  store.toggleCompare(stock)
  if (store.compareStocks.length < 2) close()
}
</script>

<template>
  <div v-if="store.showCompare" class="modal-overlay" @click.self="close">
    <div class="dialog" role="dialog" aria-modal="true" aria-label="股票对比">
      <div class="dialog-head">
        <h2>对比</h2>
        <button class="icon-btn" type="button" aria-label="关闭" @click="close">×</button>
      </div>
      <div class="dialog-body">
        <div v-if="stocks.length < 2" class="empty-state">至少选择 2 只股票。</div>
        <div v-else class="table-wrap">
          <table class="compare-table">
            <thead>
              <tr>
                <th>条件</th>
                <th v-for="stock in stocks" :key="stock.thscode">
                  <div class="compare-stock-head">
                    <strong>{{ stock.name }}</strong>
                    <span>{{ stock.thscode }} · {{ stockStatusText(stock.status) }}</span>
                    <button class="raw-toggle" type="button" @click="remove(stock)">移除</button>
                  </div>
                </th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>结论</td>
                <td v-for="stock in stocks" :key="`reason-${stock.thscode}`">
                  <div class="reason">{{ stock.summary_reason }}</div>
                </td>
              </tr>
              <tr>
                <td>数据完整度</td>
                <td v-for="stock in stocks" :key="`complete-${stock.thscode}`">
                  <span class="completeness">{{ stock.data_completeness }}</span>
                </td>
              </tr>
              <tr v-for="row in rows" :key="`${row.group}-${row.label}`">
                <td>
                  <span class="muted">{{ row.group }}</span><br />
                  {{ row.label }}
                </td>
                <td v-for="stock in stocks" :key="`${row.label}-${stock.thscode}`">
                  <template v-if="row.values[stock.thscode]">
                    <div class="value">{{ valueFor(row.values[stock.thscode]) }}</div>
                    <span
                      class="status-chip"
                      :class="row.values[stock.thscode].status"
                    >
                      {{ condStatusText(row.values[stock.thscode].status) }}
                    </span>
                  </template>
                  <span v-else class="muted">—</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>
