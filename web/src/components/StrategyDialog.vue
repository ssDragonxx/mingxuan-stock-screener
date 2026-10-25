<script setup lang="ts">
import { computed } from 'vue'
import { useScreeningStore } from '../stores/screening'

const store = useScreeningStore()

const strategyResult = computed(() => store.strategyResult)

function close() {
  store.showStrategies = false
}

function refresh() {
  store.loadStrategies()
}

function formatTime(value?: string): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { hour12: false })
}
</script>

<template>
  <div v-if="store.showStrategies" class="modal-overlay" @click.self="close">
    <div class="dialog" role="dialog" aria-modal="true" aria-label="策略库">
      <div class="dialog-head">
        <h2>策略库</h2>
        <div style="display: flex; align-items: center; gap: 8px">
          <button class="text-btn" type="button" @click="refresh">刷新</button>
          <button class="icon-btn" type="button" aria-label="关闭" @click="close">×</button>
        </div>
      </div>
      <div class="dialog-body">
        <div v-if="strategyResult" class="data-note">
          <strong>最近一次检查</strong>
          <div style="margin-top: 4px">
            <template v-if="strategyResult.diff?.first_run">
              首次运行，已记录当前入选 {{ strategyResult.summary?.included || 0 }} 只。
            </template>
            <template v-else>
              新进 {{ strategyResult.diff?.new?.length || 0 }} 只，退出
              {{ strategyResult.diff?.exit?.length || 0 }} 只；当前入选
              {{ strategyResult.summary?.included || 0 }} 只。
            </template>
          </div>
          <div v-if="strategyResult.diff?.new?.length" style="margin-top: 4px">
            新进代码：{{ strategyResult.diff.new.join('、') }}
          </div>
          <div v-if="strategyResult.diff?.exit?.length" style="margin-top: 4px">
            退出代码：{{ strategyResult.diff.exit.join('、') }}
          </div>
        </div>

        <div v-if="!store.strategies.length" class="empty-state">
          还没有保存的策略。回到结果页点击“保存策略”或“创建监控”。
        </div>
        <div v-else class="strategy-list">
          <div v-for="strategy in store.strategies" :key="strategy.id" class="strategy-item">
            <div class="strategy-item-head">
              <div>
                <h3>{{ strategy.name }}</h3>
                <div class="strategy-meta">
                  {{ strategy.query || '未记录原话' }}<br />
                  创建 {{ formatTime(strategy.created_at) }} · 最近运行
                  {{ strategy.last_run_at ? formatTime(strategy.last_run_at) : '尚未运行' }}
                </div>
              </div>
              <span class="badge" :class="strategy.monitor_enabled ? 'badge-accent' : ''">
                {{ strategy.monitor_enabled ? '每日监控' : '手动' }}
              </span>
            </div>
            <div style="margin-top: 10px; display: flex; gap: 8px">
              <button class="btn btn-secondary" type="button" @click="store.runStrategy(strategy.id)">
                立即检查
              </button>
            </div>
          </div>
        </div>
        <p class="micro-note">
          监控任务每天 18:30（Asia/Shanghai）自动重跑，并记录新进/退出。需要服务持续运行。
        </p>
      </div>
    </div>
  </div>
</template>
