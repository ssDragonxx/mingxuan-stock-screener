<script setup lang="ts">
import { computed } from 'vue'
import { useScreeningStore } from '../stores/screening'
import { formatCount, sourceStatusLabel } from '../utils'

const store = useScreeningStore()
const status = computed(() => store.dataStatus)

const datasetLabels: Record<string, string> = {
  tickers: '代码表',
  snapshot: '行情快照',
  valuation: '估值快照',
  tech_factors: '技术因子',
  industry: '行业成分',
  dividend: '股息率',
  financials: '财务指标',
}

const datasets = computed(() => Object.entries(status.value?.datasets || {}))
const isLive = computed(() => status.value?.mode === 'live')
const notReady = computed(() => isLive.value && status.value?.ready === false)

function close() {
  store.showDataDialog = false
}
</script>

<template>
  <div v-if="store.showDataDialog" class="modal-overlay" @click.self="close">
    <div class="dialog" role="dialog" aria-modal="true" aria-label="数据说明">
      <div class="dialog-head">
        <h2>数据说明</h2>
        <button class="icon-btn" type="button" aria-label="关闭" @click="close">×</button>
      </div>
      <div class="dialog-body">
        <div v-if="status?.mode === 'mock'" class="data-note">
          当前为演示数据，用于验证交互与口径展示。在 <code>.env</code> 配置
          <code>FUYAO_API_KEY</code> 并运行 <code>python -m app.data.ingest --all</code>
          后，页面会显示真实行情、估值、财务与时点。
        </div>
        <div v-if="notReady" class="data-note">
          本地数据尚未初始化：{{ status?.hint }}
          <br />
          <code>python -m app.data.ingest --all</code>
        </div>

        <h3 class="dialog-section-title">数据源与覆盖</h3>
        <div v-for="[key, dataset] in datasets" :key="key" class="data-source-row">
          <span>{{ datasetLabels[key] || key }}</span>
          <span>
            {{ formatCount(dataset.count) }} 条 · {{ dataset.as_of || '—' }} ·
            {{ sourceStatusLabel(dataset.ready ? 'ok' : 'missing') }}
          </span>
        </div>
        <div v-if="status?.financials" class="data-source-row">
          <span>财务口径</span>
          <span>
            {{ status.financials.label || status.financials.latest_report || '—' }} ·
            覆盖 {{ Math.round((status.financials.coverage || 0) * 100) }}% ·
            {{ isMock ? '演示样本' : '按需取数' }}
          </span>
        </div>

        <h3 class="dialog-section-title">数据源</h3>
        <div v-for="source in status?.sources || []" :key="source.name" class="data-source-row">
          <span>{{ source.name }}</span>
          <span>{{ sourceStatusLabel(source.status) }} · {{ source.note || '' }}</span>
        </div>

        <h3 class="dialog-section-title">口径定义</h3>
        <div
          v-for="definition in status?.definitions || []"
          :key="definition.key"
          class="data-def"
        >
          <strong>{{ definition.label }}</strong>
          <span>{{ definition.text }}</span>
        </div>

        <p v-if="status?.hint" class="micro-note" style="margin-top: 16px">{{ status.hint }}</p>
        <p class="micro-note">
          数据源：扶摇金融数据。每个数字都带字段、来源与时点；接口失败、过期或缺失不会被静默当作正常。
        </p>
      </div>
    </div>
  </div>
</template>
