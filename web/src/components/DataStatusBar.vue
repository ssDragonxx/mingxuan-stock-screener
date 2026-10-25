<script setup lang="ts">
import { computed } from 'vue'
import { useScreeningStore } from '../stores/screening'
import type { DataStatus, Summary } from '../types'
import { formatCount } from '../utils'

const props = defineProps<{
  status: DataStatus | null
  summary?: Summary | null
}>()

const store = useScreeningStore()
const isMock = computed(() => props.status?.mode === 'mock')
</script>

<template>
  <div class="data-bar">
    <span class="badge" :class="isMock ? 'badge-warn' : 'badge-accent'">
      {{ isMock ? '演示数据' : '真实数据' }}
    </span>
    <template v-if="isMock">
      <span>构造样本 · {{ formatCount(status?.universe?.count) }} 只</span>
    </template>
    <template v-else>
      <span>行情 <strong>{{ status?.quote?.as_of || '—' }}</strong></span>
      <span class="sep">·</span>
      <span>估值 <strong>{{ status?.valuation?.as_of || '—' }}</strong></span>
      <span class="sep">·</span>
      <span>财务 <strong>{{ status?.financials?.label || status?.financials?.latest_report || '—' }}</strong></span>
      <span class="sep">·</span>
      <span>全 A <strong>{{ formatCount(status?.universe?.count) }}</strong> 只</span>
    </template>
    <template v-if="summary">
      <span class="sep">·</span>
      <span>完整评估 <strong>{{ formatCount(summary.evaluated) }}</strong> 只</span>
      <span class="sep">·</span>
      <span>数据完整度 <strong>{{ summary.data_completeness }}</strong></span>
      <span v-if="summary.pending" class="badge badge-warn">
        {{ isMock ? '缺失' : '待取数' }} {{ summary.pending }}
      </span>
    </template>
    <button class="link-btn" type="button" @click="store.showDataDialog = true">
      查看数据说明
    </button>
  </div>
</template>
