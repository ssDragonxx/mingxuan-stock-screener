<script setup lang="ts">
import { computed } from 'vue'
import { useScreeningStore } from '../stores/screening'
import ConditionGroup from './ConditionGroup.vue'
import { severityLabel } from '../utils'
import type { Condition } from '../types'

const store = useScreeningStore()

const groups = computed(() => store.dsl?.groups || [])
const fieldMeta = computed(() => store.parseResult?.field_meta || {})
const assumptions = computed(() => store.parseResult?.assumptions || [])
const clarifications = computed(() => store.parseResult?.clarifications || [])
const conflicts = computed(() => store.parseResult?.conflicts || [])
const unsupported = computed(() => store.parseResult?.unsupported || [])
const summary = computed(() => store.preview?.summary || null)
const previewWarnings = computed(() => (store.preview?.warnings || []).slice(0, 2))
const parserLabel = computed(() => {
  const meta = store.parseResult?.meta
  return meta?.mode === 'llm' ? `AI 解析 · ${meta.model || 'DeepSeek'}` : '规则解析'
})
const modeLabel = computed(() => (store.dataStatus?.mode === 'mock' ? '演示样本' : '已缓存预览'))

const policyOptions = [
  { value: 'exclude_with_flag', label: '不计入（推荐）' },
  { value: 'include_with_warning', label: '计入但标记' },
  { value: 'fail', label: '直接失败' },
]

function updateCondition(conditionId: string, patch: Partial<Condition>) {
  store.updateCondition(conditionId, patch)
}

function saveDraft() {
  if (!store.dsl) return
  try {
    localStorage.setItem(
      'mingxuan:draft',
      JSON.stringify({
        query: store.query,
        dsl: store.dsl,
        savedAt: new Date().toISOString(),
      }),
    )
    store.toast('草稿已保存到本地')
  } catch {
    store.toast('本地存储不可用')
  }
}
</script>

<template>
  <section class="view active" id="view-workbench">
    <div class="view-head">
      <div>
        <button class="back-link" type="button" @click="store.setStep('intent')">
          ← 重新描述
        </button>
        <div class="query-echo">{{ store.parseResult?.query || store.query }}</div>
      </div>
      <div class="view-head-actions">
        <span class="badge">{{ parserLabel }}</span>
        <span v-if="store.dataStatus?.mode === 'mock'" class="badge badge-warn">演示数据</span>
      </div>
    </div>

    <div class="workbench-grid">
      <div class="workbench-main">
        <div class="section-head">
          <div>
            <span class="section-kicker">条件工作台</span>
            <h2>筛选条件</h2>
          </div>
          <div class="section-actions">
            <span class="muted">{{ groups.length }} 组 · {{ store.conditionCount }} 条</span>
            <button
              id="addConditionBtn"
              class="btn btn-ghost"
              type="button"
              @click="store.showAddCondition = true"
            >
              + 添加条件
            </button>
          </div>
        </div>

        <div v-if="!groups.length" class="empty-state">
          还没有条件。点击“添加条件”开始，或返回重新描述。
        </div>
        <ConditionGroup
          v-for="(group, index) in groups"
          :key="group.id"
          :group="group"
          :index="index"
          :field-meta="fieldMeta"
          @apply-option="store.applyOption"
          @update-condition="updateCondition"
          @remove-condition="store.removeCondition"
        />

        <div class="policy-card">
          <div class="policy-head">
            <div>
              <h3>缺失数据怎么办？</h3>
              <p>数据缺失、报告期未披露、PE 为负时，不应静默当作通过。当前策略会影响入选数量。</p>
            </div>
            <span class="badge badge-accent">推荐</span>
          </div>
          <div class="segmented">
            <button
              v-for="option in policyOptions"
              :key="option.value"
              type="button"
              :data-policy="option.value"
              :class="{ active: store.dsl?.missing_policy === option.value }"
              @click="store.setPolicy(option.value)"
            >
              {{ option.label }}
            </button>
          </div>
        </div>

        <div class="evidence-note">
          <span class="check-icon">✓</span>
          <span>筛选由确定性引擎执行：相同条件与数据版本，结果可复现。AI 不参与名单生成。</span>
        </div>
      </div>

      <aside class="workbench-aside">
        <div class="aside-card">
          <h3>AI 的理解</h3>
          <div v-for="(item, index) in assumptions" :key="index" class="assumption-item">
            <span class="check-icon">✓</span>
            <div>
              <div>{{ item.text }}</div>
              <div class="confidence">
                置信度 {{ Math.round((item.confidence || 0) * 100) }}%
                <template v-if="item.alternatives?.length">
                  · 可改为：{{ item.alternatives.join(' / ') }}
                </template>
              </div>
            </div>
          </div>
        </div>

        <div v-if="clarifications.length" class="aside-card">
          <h3>需要你确认</h3>
          <div
            v-for="clarification in clarifications"
            :key="clarification.id"
            class="clarification"
          >
            <p>{{ clarification.question }}</p>
            <div class="option-row">
              <button
                v-for="option in clarification.options"
                :key="option.id"
                type="button"
                class="option-chip"
                :class="{
                  active:
                    (store.clarificationChoice[clarification.id] || clarification.default) ===
                    option.id,
                }"
                @click="store.applyOption(clarification.group_id, option.id, clarification.id)"
              >
                {{ option.label }}
              </button>
            </div>
          </div>
        </div>

        <div class="aside-card">
          <h3>冲突检查</h3>
          <div v-if="!conflicts.length" class="assumption-item">
            <span class="check-icon">✓</span>
            <div>未发现明显冲突。筛选会按当前条件执行。</div>
          </div>
          <div
            v-for="conflict in conflicts"
            :key="conflict.code"
            class="conflict-item"
            :class="conflict.severity"
          >
            <strong>{{ severityLabel(conflict.severity) }}</strong>
            {{ conflict.message }}
            <span v-if="conflict.suggestion" class="conflict-suggestion">
              建议：{{ conflict.suggestion }}
            </span>
          </div>
        </div>

        <div v-if="unsupported.length" class="aside-card">
          <h3>数据能力提示</h3>
          <div v-for="item in unsupported" :key="item.phrase" class="unsupported-item">
            <strong>{{ item.phrase }}</strong>
            {{ item.reason }}
            <template v-if="item.alternatives?.length">
              <br />可用替代：{{ item.alternatives.join(' / ') }}
            </template>
          </div>
        </div>

        <div class="aside-card aside-sticky">
          <div class="preview-head">
            <span>预计结果</span>
            <span class="badge">{{ modeLabel }}</span>
          </div>
          <div class="preview-stats">
            <div>
              <strong id="previewIncluded">{{ store.previewLoading ? '…' : (summary?.included ?? '—') }}</strong>
              <span>入选</span>
            </div>
            <div>
              <strong id="previewNear">{{ store.previewLoading ? '…' : (summary?.near_miss ?? '—') }}</strong>
              <span>近邻</span>
            </div>
            <div>
              <strong id="previewUnknown">{{ store.previewLoading ? '…' : (summary?.unknown ?? '—') }}</strong>
              <span>数据不足</span>
            </div>
          </div>
          <div v-if="store.previewDelta" id="previewDelta" class="preview-delta show">
            相对初始条件：{{ store.previewDelta }}
          </div>
          <div v-if="summary" class="preview-delta show">
            前置剔除 {{ summary.cheap_excluded }} 只 · 完整评估 {{ summary.evaluated }} 只
          </div>
          <div v-if="summary?.pending" class="preview-warning show">
            <template v-if="store.dataStatus?.mode === 'live'">
              待取数 {{ summary.pending }} 只；开始筛选后会按需取财务
            </template>
            <template v-else>
              {{ summary.pending }} 只候选股财务字段缺失（演示数据）
            </template>
          </div>
          <div v-if="previewWarnings.length" class="preview-warning show">
            {{ previewWarnings.join(' · ') }}
          </div>
          <button
            id="screenBtn"
            class="btn btn-primary btn-block"
            type="button"
            :disabled="store.screenLoading || !groups.length"
            @click="store.screen()"
          >
            {{ store.screenLoading ? '筛选中…' : '开始筛选' }}
            <span v-if="!store.screenLoading" class="arrow">→</span>
          </button>
          <button class="btn btn-secondary btn-block" type="button" @click="saveDraft">
            保存草稿
          </button>
          <p class="micro-note">
            筛选是确定性的：相同条件与数据版本，结果可复现。
            <template v-if="store.dataStatus?.mode === 'live'">
              首次带财务条件时会按需取数，之后命中缓存。
            </template>
          </p>
        </div>
      </aside>
    </div>
  </section>
</template>
