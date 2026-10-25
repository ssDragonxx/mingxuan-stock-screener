<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useScreeningStore } from '../stores/screening'

const store = useScreeningStore()

const DEFAULT_VALUES: Record<string, number> = {
  revenue_yoy: 10,
  net_profit_yoy: 0,
  operating_profit_yoy: 10,
  pe_ttm: 25,
  pe_industry_pct: 60,
  pb_mrq: 3,
  volatility_60d: 30,
  max_drawdown_120d: -20,
  dividend_yield_ttm: 3,
  return_20d: -15,
  gross_margin: 30,
  net_margin: 10,
  roe: 10,
  debt_ratio: 50,
  current_ratio: 1.5,
  net_profit_cash_content: 1.0,
  ocf_to_income: 10,
  avg_turnover_20d: 1,
}

const field = ref('revenue_yoy')
const op = ref('>=')
const value = ref(10)

const fieldOptions = computed(() =>
  Object.entries(store.parseResult?.field_meta || {}).map(([key, meta]) => ({
    key,
    label: meta.label,
    meta,
  })),
)
const meta = computed(() => store.parseResult?.field_meta?.[field.value])

watch(field, () => {
  const current = meta.value
  op.value = current?.ops?.[0] || '>='
  value.value = DEFAULT_VALUES[field.value] ?? 0
})

watch(
  () => store.showAddCondition,
  (open) => {
    if (open) {
      field.value = 'revenue_yoy'
      op.value = '>='
      value.value = DEFAULT_VALUES.revenue_yoy
    }
  },
)

function submit() {
  const number = Number(value.value)
  if (!Number.isFinite(number)) {
    store.toast('阈值必须是数字')
    return
  }
  store.addCondition(field.value, op.value, number)
}

function close() {
  store.showAddCondition = false
}
</script>

<template>
  <div v-if="store.showAddCondition" class="modal-overlay" @click.self="close">
    <div class="dialog dialog-sm" role="dialog" aria-modal="true" aria-label="添加条件">
      <div class="dialog-head">
        <h2>添加条件</h2>
        <button class="icon-btn" type="button" aria-label="关闭" @click="close">×</button>
      </div>
      <form class="dialog-body" @submit.prevent="submit">
        <div class="form-field">
          <label for="newField">字段</label>
          <select id="newField" v-model="field">
            <option v-for="item in fieldOptions" :key="item.key" :value="item.key">
              {{ item.label }}
            </option>
          </select>
        </div>
        <div class="form-row">
          <div class="form-field">
            <label for="newOp">算子</label>
            <select id="newOp" v-model="op">
              <option v-for="item in meta?.ops || ['>=', '<=', '>', '<']" :key="item" :value="item">
                {{ item }}
              </option>
            </select>
          </div>
          <div class="form-field">
            <label for="newValue">阈值 <span class="muted">{{ meta?.unit || '' }}</span></label>
            <input
              id="newValue"
              v-model.number="value"
              type="number"
              :step="meta?.step ?? 1"
              :min="meta?.min ?? undefined"
              :max="meta?.max ?? undefined"
            />
          </div>
        </div>
        <p class="micro-note">{{ meta?.desc }}</p>
        <div class="dialog-actions">
          <button class="btn btn-secondary" type="button" @click="close">取消</button>
          <button class="btn btn-primary" type="submit">添加</button>
        </div>
      </form>
    </div>
  </div>
</template>
