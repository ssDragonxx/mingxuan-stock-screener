<script setup lang="ts">
import { onMounted } from 'vue'
import { useScreeningStore } from './stores/screening'
import AppHeader from './components/AppHeader.vue'
import AppFooter from './components/AppFooter.vue'
import IntentView from './components/IntentView.vue'
import ConditionView from './components/ConditionView.vue'
import ResultView from './components/ResultView.vue'
import EvidenceDrawer from './components/EvidenceDrawer.vue'
import DataDialog from './components/DataDialog.vue'
import AddConditionDialog from './components/AddConditionDialog.vue'
import StrategyDialog from './components/StrategyDialog.vue'
import CompareDialog from './components/CompareDialog.vue'
import ProgressOverlay from './components/ProgressOverlay.vue'
import ToastHost from './components/ToastHost.vue'

const store = useScreeningStore()

onMounted(() => {
  store.loadStatus()
})
</script>

<template>
  <AppHeader />

  <div
    v-if="store.dataStatus?.mode === 'live' && store.dataStatus?.ready === false"
    class="container"
  >
    <div class="banner banner-warn">
      <strong>本地数据尚未初始化</strong>
      <span>{{ store.dataStatus?.hint }}</span>
      <code>python -m app.data.ingest --all</code>
    </div>
  </div>

  <main class="container">
    <IntentView v-if="store.step === 'intent'" />
    <ConditionView v-else-if="store.step === 'conditions'" />
    <ResultView v-else />
  </main>

  <AppFooter />
  <EvidenceDrawer />
  <DataDialog />
  <AddConditionDialog />
  <StrategyDialog />
  <CompareDialog />
  <ProgressOverlay />
  <ToastHost />
</template>
