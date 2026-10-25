<script setup lang="ts">
import { computed, ref } from 'vue'
import { useScreeningStore } from '../stores/screening'
import DataStatusBar from './DataStatusBar.vue'
import ResultTable from './ResultTable.vue'
import SensitivityChart from './SensitivityChart.vue'
import { formatCount } from '../utils'
import { buildResultCsv, downloadCsv } from '../csv'
import type { StockResult } from '../types'

const store = useScreeningStore()
const result = computed(() => store.screenResult)
const summary = computed(() => result.value?.summary || null)
const funnel = computed(() => result.value?.funnel || [])
const included = computed(
  () => (result.value?.stocks || []).filter((stock) => stock.status === 'included'),
)
const near = computed(
  () => (result.value?.stocks || []).filter((stock) => stock.status === 'near_miss'),
)
const excluded = computed(
  () => (result.value?.stocks || []).filter((stock) => stock.status === 'excluded'),
)
const unknown = computed(
  () => (result.value?.stocks || []).filter((stock) => stock.status === 'unknown'),
)
const breakdown = computed(() => result.value?.excluded_breakdown || [])
const maxBreakdown = computed(() => Math.max(...breakdown.value.map((item) => item.count), 1))
const sensitivity = computed(() => result.value?.sensitivity || [])
const binding = computed(() => sensitivity.value.find((item) => item.binding))
const warnings = computed(() => result.value?.warnings || [])
const dataStatus = computed(() => result.value?.data_status || store.dataStatus)

const diagnoseQuery = ref('')

function openStock(stock: StockResult) {
  store.openDrawer(stock)
}

function runDiagnose() {
  const query = diagnoseQuery.value.trim()
  if (!query) {
    store.toast('请输入股票代码或名称')
    return
  }
  store.diagnose(query)
}

function saveStrategy() {
  const name = window.prompt('策略名称', store.query || '未命名策略')
  if (name) store.saveStrategy(name, false)
}

function createMonitor() {
  const name = window.prompt('监控名称', store.query || '未命名监控')
  if (name) store.saveStrategy(name, true)
}

function exportCsv() {
  const data = result.value
  if (!data || !data.stocks.length) {
    store.toast('没有可导出的结果')
    return
  }
  const csv = buildResultCsv(data, store.parseResult?.field_meta || {})
  const now = new Date()
  const stamp = [
    now.getFullYear(),
    String(now.getMonth() + 1).padStart(2, '0'),
    String(now.getDate()).padStart(2, '0'),
  ].join('')
  const time = `${String(now.getHours()).padStart(2, '0')}${String(now.getMinutes()).padStart(2, '0')}`
  downloadCsv(`明选筛选_${stamp}_${time}.csv`, csv)
  store.toast(`已导出 ${data.stocks.length} 只股票`)
}
</script>

<template>
  <section class="view active" id="view-results">
    <div class="view-head">
      <div>
        <button class="back-link" type="button" @click="store.setStep('conditions')">
          ← 修改条件
        </button>
        <div class="query-echo">{{ store.parseResult?.query || store.query }}</div>
      </div>
      <div class="view-head-actions">
        <button class="btn btn-secondary" type="button" @click="saveStrategy">保存策略</button>
        <button class="btn btn-primary" type="button" @click="createMonitor">创建监控</button>
      </div>
    </div>

    <div v-if="!result" class="empty-state">没有筛选结果，请返回修改条件。</div>

    <template v-else>
      <DataStatusBar :status="dataStatus" :summary="summary" />

      <div v-if="warnings.length" class="warnings-list">
        <div v-for="warning in warnings" :key="warning" class="warning-item">{{ warning }}</div>
      </div>

      <div class="funnel">
        <template v-for="(step, index) in funnel" :key="step.label">
          <div class="funnel-step">
            <strong>{{ formatCount(step.count) }}</strong>
            <span>{{ step.label }}</span>
          </div>
          <span v-if="index < funnel.length - 1" class="funnel-arrow">→</span>
        </template>
        <span v-if="summary?.cheap_excluded" class="badge badge-warn">
          前置剔除 {{ summary.cheap_excluded }}
        </span>
      </div>

      <div class="stat-grid">
        <div class="stat-card included">
          <div class="stat-label">入选</div>
          <div class="stat-value">{{ summary?.included ?? '—' }}</div>
          <div class="stat-sub">全部条件通过</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">近邻</div>
          <div class="stat-value">{{ summary?.near_miss ?? '—' }}</div>
          <div class="stat-sub">只差 1 项</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">未入选</div>
          <div class="stat-value">{{ summary?.excluded ?? '—' }}</div>
          <div class="stat-sub">含前置条件剔除</div>
        </div>
        <div class="stat-card unknown">
          <div class="stat-label">数据不足</div>
          <div class="stat-value">{{ summary?.unknown ?? '—' }}</div>
          <div class="stat-sub">无失败项，但数据缺失</div>
        </div>
      </div>

      <div class="tabs" role="tablist">
        <button
          class="tab"
          data-tab="included"
          :class="{ active: store.activeTab === 'included' }"
          type="button"
          @click="store.setTab('included')"
        >
          入选 <span>{{ summary?.included ?? 0 }}</span>
        </button>
        <button
          class="tab"
          data-tab="near_miss"
          :class="{ active: store.activeTab === 'near_miss' }"
          type="button"
          @click="store.setTab('near_miss')"
        >
          近邻 <span>{{ summary?.near_miss ?? 0 }}</span>
        </button>
        <button
          class="tab"
          data-tab="excluded"
          :class="{ active: store.activeTab === 'excluded' }"
          type="button"
          @click="store.setTab('excluded')"
        >
          未入选 <span>{{ summary?.excluded ?? 0 }}</span>
        </button>
        <button
          class="tab"
          data-tab="unknown"
          :class="{ active: store.activeTab === 'unknown' }"
          type="button"
          @click="store.setTab('unknown')"
        >
          数据不足 <span>{{ summary?.unknown ?? 0 }}</span>
        </button>
        <button
          class="tab"
          data-tab="sensitivity"
          :class="{ active: store.activeTab === 'sensitivity' }"
          type="button"
          @click="store.setTab('sensitivity')"
        >
          敏感性
        </button>
      </div>

      <div v-if="store.activeTab !== 'sensitivity'" class="table-legend">
        <span><i class="dot-status pass"></i> 通过</span>
        <span><i class="dot-status fail"></i> 不通过</span>
        <span><i class="dot-status unknown"></i> 未知 / 缺失</span>
        <span class="legend-note">点击任意一行查看逐条证据 · 表格可横滑</span>
      </div>

      <div class="tab-panel" :class="{ active: store.activeTab === 'included' }">
        <ResultTable
          :stocks="included"
          reason-header="入选理由"
          empty-text="没有股票通过全部条件。可以回到条件工作台放宽一项，或调整缺失数据策略。"
          @row-click="openStock"
        />
      </div>

      <div class="tab-panel" :class="{ active: store.activeTab === 'near_miss' }">
        <ResultTable
          :stocks="near"
          reason-header="差距"
          empty-text="没有只差一项的股票。"
          @row-click="openStock"
        />
      </div>

      <div class="tab-panel" :class="{ active: store.activeTab === 'excluded' }">
        <div class="breakdown-card">
          <h3>未通过条件分布</h3>
          <p class="sub">
            一只股票可能同时不满足多条条件。“含缺失项”统计任一条件缺失的股票，与“数据不足”Tab
            的口径不同。
          </p>
          <div
            v-for="item in breakdown"
            :key="`${item.field}-${item.kind}`"
            class="bar-row"
          >
            <span>{{ item.label }}</span>
            <div class="bar-track">
              <div
                class="bar-fill"
                :class="{ unknown: item.kind === 'unknown' }"
                :style="{ width: `${Math.max(2, (item.count / maxBreakdown) * 100)}%` }"
              ></div>
            </div>
            <span class="bar-count">{{ item.count }}</span>
          </div>
          <div v-if="!breakdown.length" class="muted">暂无可统计的未通过条件。</div>
          <div class="diagnose-box">
            <input
              v-model="diagnoseQuery"
              type="text"
              autocomplete="off"
              placeholder="输入股票代码或名称，诊断为什么没入选，例如 600036"
              @keydown.enter="runDiagnose"
            />
            <button
              class="btn btn-secondary"
              type="button"
              :disabled="store.diagnoseLoading"
              @click="runDiagnose"
            >
              {{ store.diagnoseLoading ? '诊断中…' : '诊断' }}
            </button>
          </div>
        </div>
        <ResultTable
          :stocks="excluded"
          reason-header="未入选原因"
          empty-text="没有未入选股票。"
          @row-click="openStock"
        />
      </div>

      <div class="tab-panel" :class="{ active: store.activeTab === 'unknown' }">
        <div class="unknown-note">
          <span>这些股票并非被判定为不合格，而是数据缺失或口径不适用。默认不计入入选。</span>
          <button type="button" @click="store.setStep('conditions')">调整缺失策略</button>
        </div>
        <ResultTable
          :stocks="unknown"
          reason-header="缺失字段"
          empty-text="没有数据不足的股票。"
          @row-click="openStock"
        />
      </div>

      <div class="tab-panel" :class="{ active: store.activeTab === 'sensitivity' }">
        <template v-if="sensitivity.length">
          <div class="binding-card">
            <template v-if="binding">
              <div>
                <h3>最卡条件：{{ binding.label }}</h3>
                <p>
                  当前阈值 {{ binding.current }}{{ binding.unit }}；放宽到
                  {{ binding.relax_to }}{{ binding.unit }}，预计入选 +{{ binding.delta }}
                </p>
              </div>
              <div class="big">+{{ binding.delta }}</div>
            </template>
            <template v-else>
              <div>
                <h3>当前条件下，没有明显的单一卡点</h3>
                <p>调整任一阈值对入选数量的影响都较小；可以尝试组合放宽。</p>
              </div>
              <div class="big">—</div>
            </template>
          </div>
          <div class="sensitivity-grid">
            <div
              v-for="item in sensitivity"
              :key="item.condition_id"
              class="sensitivity-card"
              :class="{ 'is-binding': item.binding }"
            >
              <div class="sensitivity-head">
                <h3>{{ item.label }}</h3>
                <span class="current">当前 {{ item.current }}{{ item.unit }}</span>
              </div>
              <SensitivityChart :item="item" />
              <p class="sensitivity-note">
                {{ item.binding ? '放宽该条件对入选数量影响最大。' : '单独调整该条件的影响较小。' }}
                结果为当前候选集上的模拟。
              </p>
            </div>
          </div>
          <p class="sensitivity-note">
            敏感性分析一次只改变一个条件，其余条件保持不变；它不代表未来收益。
          </p>
        </template>
        <div v-else class="empty-state">当前条件没有可扫描的数值阈值。</div>
      </div>

      <div class="next-actions">
        <button class="btn btn-secondary" type="button" @click="exportCsv">导出 CSV</button>
        <button class="btn btn-secondary" type="button" @click="createMonitor">
          创建监控任务
        </button>
        <span class="muted" style="align-self: center">
          监控任务每日 18:30 自动检查。
        </span>
      </div>

      <div v-if="store.compareStocks.length" class="compare-bar">
        <div class="compare-chips">
          <span v-for="stock in store.compareStocks" :key="stock.thscode" class="compare-chip">
            {{ stock.name }}
            <button type="button" @click="store.toggleCompare(stock)">×</button>
          </span>
        </div>
        <div class="compare-actions">
          <button class="btn btn-secondary" type="button" @click="store.clearCompare()">
            清空
          </button>
          <button class="btn btn-primary" type="button" @click="store.openCompare()">
            对比 {{ store.compareStocks.length }} 只
          </button>
        </div>
      </div>
    </template>
  </section>
</template>
