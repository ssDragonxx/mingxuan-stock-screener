<script setup lang="ts">
import { computed, ref } from 'vue'
import { useScreeningStore } from '../stores/screening'

const store = useScreeningStore()
const query = ref(store.query || '经营改善、估值合理、走势相对稳定')

const examples = [
  { label: '经营改善 · 估值合理 · 走势稳定', text: '经营改善、估值合理、走势相对稳定' },
  { label: '高股息 · 低波动 · 现金流健康', text: '高股息、低波动、现金流健康' },
  { label: '近 20 日超跌 · 基本面未恶化', text: '近20日超跌，但基本面没有恶化' },
  { label: '估值合理 · 连续分红', text: '估值合理、连续分红' },
]

const isMock = computed(() => store.dataStatus?.mode === 'mock')
const liveNotReady = computed(
  () => store.dataStatus?.mode === 'live' && store.dataStatus?.ready === false,
)

function useExample(text: string) {
  query.value = text
  document.getElementById('queryInput')?.focus()
}

function submit() {
  store.parse(query.value)
}
</script>

<template>
  <section class="view active" id="view-intent">
    <div class="intent-hero">
      <div class="eyebrow"><span class="eyebrow-dot"></span> 自然语言选股 · 证据可追溯</div>
      <h1>把你的选股想法，<br />变成可检查的条件。</h1>
      <p class="hero-sub">
        说出“经营改善、估值合理、走势相对稳定”，明选会把它拆成一条条可修改的条件，并用可追溯的数据逐条验证。
      </p>
    </div>

    <div class="intent-card">
      <label class="sr-only" for="queryInput">选股想法</label>
      <textarea
        id="queryInput"
        v-model="query"
        maxlength="500"
        placeholder="例如：经营改善、估值合理、走势相对稳定"
        @keydown.ctrl.enter="submit"
        @keydown.meta.enter="submit"
      ></textarea>
      <div class="example-row">
        <span class="example-label">试试</span>
        <button
          v-for="example in examples"
          :key="example.text"
          class="chip example-chip"
          type="button"
          @click="useExample(example.text)"
        >
          {{ example.label }}
        </button>
      </div>
      <div class="intent-actions">
        <div class="universe-hint">
          <span class="mini-label">数据范围</span>
          <div class="universe-row">
            <select v-model="store.universe" class="select-sm" aria-label="数据范围">
              <option value="all_a_share">全 A 股</option>
              <option value="csi300">沪深 300</option>
              <option value="csi500">中证 500</option>
              <option value="csi1000">中证 1000</option>
            </select>
            <span>剔除 ST / 停牌 / 次新</span>
          </div>
        </div>
        <button id="parseBtn" class="btn btn-primary" type="button" :disabled="store.parseLoading" @click="submit">
          {{ store.parseLoading ? '解析中…' : '解析意图' }}
          <span v-if="!store.parseLoading" class="arrow">→</span>
        </button>
      </div>
      <div class="prototype-note">
        <template v-if="isMock">
          当前为演示数据；在 <code>.env</code> 配置 FUYAO_API_KEY 并运行
          <code>python -m app.data.ingest --all</code> 后接入真实数据。
        </template>
        <template v-else-if="liveNotReady">
          本地数据尚未初始化：{{ store.dataStatus?.hint }}
        </template>
        <template v-else>
          真实数据模式：行情/估值全市场，财务按需取数并缓存；首次筛选可能需要 20–40 秒。
        </template>
      </div>
    </div>

    <div class="feature-grid">
      <article class="feature-card">
        <span class="feature-index">01</span>
        <h3>说人话</h3>
        <p>模糊词自动拆成字段、阈值和时间窗，并标出 AI 的假设与不确定处。</p>
      </article>
      <article class="feature-card">
        <span class="feature-index">02</span>
        <h3>看得见</h3>
        <p>每条条件都有值、阈值、来源和时点；缺失数据单独标记，不静默通过。</p>
      </article>
      <article class="feature-card">
        <span class="feature-index">03</span>
        <h3>改得动</h3>
        <p>改一个阈值，先看候选数量和结构变化，再决定是否应用。</p>
      </article>
    </div>
  </section>
</template>
