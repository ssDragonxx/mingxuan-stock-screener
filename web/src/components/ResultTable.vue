<script setup lang="ts">
import type { StockResult } from '../types'
import { condStatusText, stockStatusText } from '../utils'

withDefaults(
  defineProps<{
    stocks: StockResult[]
    reasonHeader?: string
    showStatus?: boolean
    emptyText?: string
  }>(),
  {
    reasonHeader: '入选理由',
    showStatus: false,
    emptyText: '暂无数据',
  },
)

const emit = defineEmits<{
  (event: 'row-click', stock: StockResult): void
}>()

function dotTitle(condition: StockResult['conditions'][number]): string {
  const suffix = condition.gap_text ? `（${condition.gap_text}）` : ''
  return `${condition.field_label}：${condStatusText(condition.status)}${suffix}`
}
</script>

<template>
  <div v-if="!stocks.length" class="empty-state">{{ emptyText }}</div>
  <div v-else class="table-card">
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>股票</th>
            <th>行业</th>
            <th v-if="showStatus">状态</th>
            <th>{{ reasonHeader }}</th>
            <th>条件状态</th>
            <th>完整度</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="stock in stocks"
            :key="stock.thscode"
            :data-thscode="stock.thscode"
            @click="emit('row-click', stock)"
          >
            <td>
              <div class="stock-name">
                <strong>{{ stock.name }}</strong>
                <span>{{ stock.thscode }}</span>
              </div>
            </td>
            <td><span class="industry">{{ stock.industry }}</span></td>
            <td v-if="showStatus">
              <span class="status-chip" :class="stock.status">
                {{ stockStatusText(stock.status) }}
              </span>
            </td>
            <td><div class="reason">{{ stock.summary_reason }}</div></td>
            <td>
              <div class="condition-dots">
                <span
                  v-for="condition in stock.conditions"
                  :key="condition.condition_id"
                  class="dot-status"
                  :class="condition.status"
                  :title="dotTitle(condition)"
                ></span>
              </div>
            </td>
            <td><span class="completeness">{{ stock.data_completeness }}</span></td>
            <td><span class="row-arrow">→</span></td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
