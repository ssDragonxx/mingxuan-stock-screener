<script setup lang="ts">
import { computed } from 'vue'
import { useScreeningStore } from '../stores/screening'

const store = useScreeningStore()

const progress = computed(() => {
  const job = store.job
  if (!job) return { percent: 6, message: '正在创建筛选任务…' }
  const { done, total, message } = job.progress || { done: 0, total: 1, message: '筛选中…' }
  const percent =
    total > 0
      ? Math.min(100, Math.max(4, Math.round((done / total) * 100)))
      : job.status === 'running'
        ? 30
        : 6
  return { percent, message: message || '筛选中…' }
})
</script>

<template>
  <div v-if="store.screenLoading || store.screenError" class="progress-overlay">
    <div class="progress-card">
      <template v-if="store.screenLoading">
        <div class="spinner"></div>
        <h3>正在筛选</h3>
        <p class="progress-message">{{ progress.message }}</p>
        <div class="progress-track">
          <div class="progress-bar" :style="{ width: `${progress.percent}%` }"></div>
        </div>
        <div class="progress-meta">
          {{ progress.percent }}% · 首次带财务条件时可能需要 20–40 秒，之后命中缓存会快很多
        </div>
        <button class="btn btn-secondary" type="button" @click="store.cancelScreen()">
          停止等待
        </button>
      </template>
      <template v-else>
        <h3>筛选未完成</h3>
        <p class="error-text">{{ store.screenError?.message }}</p>
        <p v-if="store.screenError?.hint" class="micro-note">{{ store.screenError.hint }}</p>
        <button class="btn btn-primary" type="button" @click="store.screenError = null">
          知道了
        </button>
      </template>
    </div>
  </div>
</template>
