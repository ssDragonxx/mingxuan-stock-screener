<script setup lang="ts">
import { useScreeningStore } from '../stores/screening'

const store = useScreeningStore()

function openStrategies() {
  store.loadStrategies()
  store.showStrategies = true
}
</script>

<template>
  <header class="site-header">
    <div class="container header-inner">
      <a class="brand" href="#" @click.prevent="store.setStep('intent')">
        <span class="brand-mark">明</span>
        <span class="brand-text"><strong>明选</strong><small>选股意图编译器</small></span>
      </a>
      <div class="header-right">
        <button class="data-pill" type="button" @click="store.showDataDialog = true">
          <span class="dot"></span>
          <span v-if="store.dataStatus?.mode === 'mock'">演示数据 · 构造样本</span>
          <span v-else-if="store.dataStatus?.universe?.count">
            全 A {{ store.dataStatus.universe.count.toLocaleString('zh-CN') }} 只
          </span>
          <span v-else>数据未初始化</span>
        </button>
        <button class="text-btn" type="button" @click="openStrategies">策略库</button>
        <button class="text-btn" type="button" @click="store.showDataDialog = true">数据说明</button>
        <span class="version-badge">v0.2</span>
      </div>
    </div>
  </header>
</template>
