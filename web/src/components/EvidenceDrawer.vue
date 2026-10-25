<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useScreeningStore } from '../stores/screening'
import {
  condStatusText,
  fmtValue,
  statusIcon,
  stockStatusText,
  thresholdLabel,
} from '../utils'
import type { Evidence } from '../types'

const store = useScreeningStore()
const rawOpen = ref(false)

watch(
  () => store.drawerStock,
  () => {
    rawOpen.value = false
  },
)

const stock = computed(() => store.drawerStock)
const groups = computed(() => {
  const list: { group_id: string; group_label: string; items: Evidence[] }[] = []
  for (const condition of stock.value?.conditions || []) {
    let group = list.find((item) => item.group_id === condition.group_id)
    if (!group) {
      group = {
        group_id: condition.group_id,
        group_label: condition.group_label,
        items: [],
      }
      list.push(group)
    }
    group.items.push(condition)
  }
  return list
})
const rawJson = computed(() => JSON.stringify(stock.value?.raw || {}, null, 2))

function valueFor(item: Evidence) {
  return fmtValue(item.value, item.field, store.parseResult?.field_meta?.[item.field])
}

function addCompare() {
  if (!stock.value) return
  store.toggleCompare(stock.value)
  store.closeDrawer()
}
</script>

<template>
  <div
    v-if="store.drawerOpen && stock"
    id="drawerOverlay"
    class="drawer-overlay open"
    @click="store.closeDrawer()"
  ></div>
  <aside
    v-if="store.drawerOpen && stock"
    id="drawer"
    class="drawer open"
    aria-hidden="false"
    aria-label="股票证据详情"
    @click.stop
  >
    <div class="drawer-header">
      <div class="drawer-title">
        <h2>{{ stock.name }}</h2>
        <div class="stock-code">
          <span>{{ stock.thscode }} · {{ stock.industry }}</span>
          <span class="status-chip" :class="stock.status">
            {{ stockStatusText(stock.status) }}
          </span>
        </div>
      </div>
      <button id="closeDrawerBtn" class="icon-btn" type="button" aria-label="关闭" @click="store.closeDrawer()">
        ×
      </button>
    </div>

    <div class="drawer-body">
      <div class="drawer-summary">
        <span class="status-chip" :class="stock.status">
          {{ stockStatusText(stock.status) }}
        </span>
        <span style="margin-left: 8px">{{ stock.summary_reason }}</span>
      </div>

      <div class="drawer-section">
        <h3>逐条件证据</h3>
        <div
          v-for="group in groups"
          :key="group.group_id"
          class="evidence-group"
        >
          <div class="evidence-group-head">
            <span>{{ group.group_label }}</span>
            <span class="badge">
              {{ group.items.filter((item) => item.status === 'pass').length }}/{{ group.items.length }} 通过
            </span>
          </div>
          <div
            v-for="item in group.items"
            :key="item.condition_id"
            class="evidence-row"
          >
            <span class="evidence-icon" :class="item.status">{{ statusIcon(item.status) }}</span>
            <div class="evidence-main">
              <div>
                <span class="label">{{ item.field_label }}</span>
                <span class="value">{{ valueFor(item) }}</span>
                <span class="threshold">{{ thresholdLabel(item) }}</span>
              </div>
              <div class="meta">
                {{ item.source }} · {{ item.as_of }}
                <template v-if="item.note"> · {{ item.note }}</template>
              </div>
              <div v-if="item.status === 'fail' && item.gap_text" class="gap">
                {{ item.gap_text }}
              </div>
              <div v-if="item.status === 'unknown'" class="missing">
                {{ item.gap_text || '数据不足' }}
              </div>
            </div>
            <span class="status-chip" :class="item.status">
              {{ condStatusText(item.status) }}
            </span>
          </div>
        </div>
      </div>

      <div v-if="stock.risk_flags?.length" class="drawer-section">
        <h3>风险与未知</h3>
        <div class="risk-list">
          <div v-for="flag in stock.risk_flags" :key="flag" class="risk-item">{{ flag }}</div>
        </div>
      </div>

      <div class="drawer-section">
        <h3>AI 分析</h3>
        <p class="micro-note" style="margin: 0 0 8px">
          基于行情、估值、技术面、全部财务指标、近 4 期趋势与当前筛选条件生成；数字会逐个校验。
        </p>
        <button
          id="explainBtn"
          class="btn btn-secondary"
          type="button"
          :disabled="store.explainLoading"
          @click="store.explainCurrent()"
        >
          {{
            store.explainLoading
              ? '分析中…'
              : store.explanation
                ? '重新分析'
                : '生成分析'
          }}
        </button>
        <div v-if="store.explanation" class="explain-box" style="margin-top: 10px">
          <div class="explain-mode">
            {{
              store.explanation.mode === 'llm'
                ? 'DeepSeek 生成 · 已做数字校验'
                : `模板生成 · ${store.explanation.fallback_reason || '未配置 DeepSeek 或校验未通过'}`
            }}
          </div>
          <div v-if="store.explanation.facts_used" class="explain-facts">
            分析依据：{{ store.explanation.facts_used.indicators }} 项财务指标 ·
            {{ store.explanation.facts_used.periods }} 期趋势 ·
            {{ store.explanation.facts_used.conditions }} 条筛选条件
          </div>
          <template v-if="store.explanation.sections?.length">
            <div
              v-for="section in store.explanation.sections"
              :key="section.title"
              class="explain-section"
            >
              <h4>{{ section.title }}</h4>
              <p>{{ section.text }}</p>
            </div>
          </template>
          <template v-else>{{ store.explanation.text }}</template>
        </div>
      </div>

      <div class="drawer-section">
        <button class="raw-toggle" type="button" @click="rawOpen = !rawOpen">
          {{ rawOpen ? '收起原始响应' : '查看原始响应' }}
        </button>
        <pre v-if="rawOpen" class="raw-box open">{{ rawJson }}</pre>
      </div>
    </div>

    <div class="drawer-footer">
      <button id="compareBtn" class="btn btn-secondary" type="button" @click="addCompare">加入对比</button>
      <button
        class="btn btn-secondary"
        type="button"
        @click="store.toast('已加入观察（原型）')"
      >
        加入观察
      </button>
      <button
        class="btn btn-primary"
        type="button"
        @click="store.toast('诊断已记录到本地')"
      >
        保存诊断
      </button>
    </div>
  </aside>
</template>
