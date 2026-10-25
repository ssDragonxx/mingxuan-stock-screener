import { defineStore } from 'pinia'
import * as api from '../api/client'
import type {
  Condition,
  DataStatus,
  DSL,
  Explanation,
  Group,
  GroupOption,
  Job,
  ParseResult,
  PreviewResult,
  ScreenResult,
  StockResult,
  Strategy,
  Summary,
  Toast,
} from '../types'

let toastCounter = 0
let previewTimer: ReturnType<typeof setTimeout> | null = null
let pollTimer: ReturnType<typeof setTimeout> | null = null

export const useScreeningStore = defineStore('screening', {
  state: () => ({
    step: 'intent' as 'intent' | 'conditions' | 'results',
    query: '',
    universe: 'all_a_share',
    parseResult: null as ParseResult | null,
    dsl: null as DSL | null,
    preview: null as PreviewResult | null,
    baselineSummary: null as Summary | null,
    previewLoading: false,
    parseLoading: false,
    screenLoading: false,
    job: null as Job | null,
    screenError: null as { message: string; hint?: string } | null,
    screenResult: null as ScreenResult | null,
    activeTab: 'included' as 'included' | 'near_miss' | 'excluded' | 'unknown' | 'sensitivity',
    dataStatus: null as DataStatus | null,
    showDataDialog: false,
    showAddCondition: false,
    showStrategies: false,
    showCompare: false,
    drawerStock: null as StockResult | null,
    drawerOpen: false,
    explanation: null as Explanation | null,
    explainLoading: false,
    compareStocks: [] as StockResult[],
    strategies: [] as Strategy[],
    strategiesLoading: false,
    strategyResult: null as any,
    toasts: [] as Toast[],
    clarificationChoice: {} as Record<string, string>,
    diagnoseLoading: false,
  }),

  getters: {
    isLive(state): boolean {
      return state.dataStatus?.mode === 'live'
    },
    dataReady(state): boolean {
      return Boolean(state.dataStatus?.ready)
    },
    previewDelta(state): string | null {
      if (!state.preview || !state.baselineSummary) return null
      const labels: [keyof Summary, string][] = [
        ['included', '入选'],
        ['near_miss', '近邻'],
        ['unknown', '数据不足'],
      ]
      const parts = labels
        .map(([key, label]) => {
          const change = Number(state.preview!.summary[key]) - Number(state.baselineSummary![key])
          if (!change) return null
          return `${label} ${change > 0 ? '+' : ''}${change}`
        })
        .filter(Boolean)
      return parts.length ? parts.join(' · ') : null
    },
    conditionCount(state): number {
      return (state.dsl?.groups || []).reduce((sum, group) => sum + group.conditions.length, 0)
    },
    includedStocks(state): StockResult[] {
      return (state.screenResult?.stocks || []).filter((stock) => stock.status === 'included')
    },
  },

  actions: {
    toast(message: string) {
      const id = ++toastCounter
      this.toasts.push({ id, message })
      setTimeout(() => {
        this.toasts = this.toasts.filter((item) => item.id !== id)
      }, 3000)
    },

    async loadStatus() {
      try {
        this.dataStatus = await api.getStatus()
      } catch (error) {
        this.toast((error as Error).message || '无法获取数据状态')
      }
    },

    setStep(step: 'intent' | 'conditions' | 'results') {
      this.step = step
      window.scrollTo({ top: 0, behavior: 'smooth' })
    },

    setTab(tab: 'included' | 'near_miss' | 'excluded' | 'unknown' | 'sensitivity') {
      this.activeTab = tab
    },

    setUniverse(universe: string) {
      this.universe = universe
    },

    async parse(query: string) {
      const text = (query || '').trim()
      if (!text) {
        this.toast('请先描述你的选股想法')
        return
      }
      this.parseLoading = true
      this.screenError = null
      this.query = text
      try {
        const result = await api.parseIntent(text, this.universe)
        this.parseResult = result
        this.dsl = JSON.parse(JSON.stringify(result.dsl)) as DSL
        this.baselineSummary = null
        this.preview = null
        this.screenResult = null
        this.clarificationChoice = {}
        for (const clarification of result.clarifications || []) {
          this.clarificationChoice[clarification.id] = clarification.default
        }
        this.step = 'conditions'
        await this.refreshPreview()
      } catch (error) {
        const payload = (error as any)?.payload
        this.screenError = {
          message: (error as Error).message,
          hint: payload?.error?.hint || payload?.detail?.hint,
        }
        this.toast((error as Error).message || '解析失败')
      } finally {
        this.parseLoading = false
      }
    },

    async refreshPreview() {
      if (!this.dsl) return
      this.previewLoading = true
      try {
        const result = await api.preview(this.dsl)
        this.preview = result
        if (!this.baselineSummary) {
          this.baselineSummary = { ...result.summary }
        }
        this.screenError = null
      } catch (error) {
        const payload = (error as any)?.payload
        this.preview = null
        this.screenError = {
          message: (error as Error).message,
          hint: payload?.error?.hint || payload?.detail?.hint,
        }
      } finally {
        this.previewLoading = false
      }
    },

    schedulePreview() {
      if (previewTimer) clearTimeout(previewTimer)
      previewTimer = setTimeout(() => {
        this.refreshPreview()
      }, 260)
    },

    findGroup(groupId: string): Group | undefined {
      return this.dsl?.groups.find((group) => group.id === groupId)
    },

    findCondition(conditionId: string): { group: Group; condition: Condition } | null {
      for (const group of this.dsl?.groups || []) {
        const condition = group.conditions.find((item) => item.id === conditionId)
        if (condition) return { group, condition }
      }
      return null
    },

    applyOption(groupId: string, optionId: string, clarificationId?: string) {
      const group = this.findGroup(groupId)
      if (!group) return
      const option = (group.options || []).find((item) => item.id === optionId) as GroupOption | undefined
      if (!option) return

      if (Array.isArray(option.conditions)) {
        group.conditions = option.conditions.map((condition) => ({ ...condition }))
      } else if (option.replace_condition) {
        const index = group.conditions.findIndex((condition) => condition.id === option.replace_condition!.id)
        if (index < 0) {
          this.toast('该口径对应的条件已被删除')
          return
        }
        group.conditions[index] = { ...option.replace_condition }
      } else if (option.set_value !== undefined) {
        if (!group.conditions[0]) {
          this.toast('该口径对应的条件已被删除')
          return
        }
        group.conditions[0].value = option.set_value
      } else {
        this.toast('该选项暂未实现')
        return
      }

      group.definition = optionId
      if (clarificationId) {
        this.clarificationChoice[clarificationId] = optionId
      } else {
        const clarification = (this.parseResult?.clarifications || []).find(
          (item) => item.group_id === groupId,
        )
        if (clarification) this.clarificationChoice[clarification.id] = optionId
      }
      this.schedulePreview()
    },

    updateCondition(conditionId: string, patch: Partial<Condition>) {
      const found = this.findCondition(conditionId)
      if (!found) return
      Object.assign(found.condition, patch)
      this.schedulePreview()
    },

    removeCondition(conditionId: string) {
      if (!this.dsl) return
      for (let index = 0; index < this.dsl.groups.length; index += 1) {
        const group = this.dsl.groups[index]
        const conditionIndex = group.conditions.findIndex((item) => item.id === conditionId)
        if (conditionIndex >= 0) {
          group.conditions.splice(conditionIndex, 1)
          if (!group.conditions.length) this.dsl.groups.splice(index, 1)
          break
        }
      }
      if (this.parseResult?.clarifications) {
        const groupIds = new Set(this.dsl.groups.map((group) => group.id))
        this.parseResult.clarifications = this.parseResult.clarifications.filter((item) =>
          groupIds.has(item.group_id),
        )
      }
      this.schedulePreview()
    },

    addCondition(field: string, op: string, value: number) {
      if (!this.dsl || !this.parseResult) return
      const meta = this.parseResult.field_meta[field]
      if (!meta) {
        this.toast('字段不存在')
        return
      }
      let group = this.dsl.groups.find((item) => item.id === 'g_custom')
      if (!group) {
        group = {
          id: 'g_custom',
          label: '自定义条件',
          logic: 'AND',
          source_phrase: '手动添加',
          conditions: [],
          definition: 'custom',
        }
        this.dsl.groups.push(group)
      }
      group.conditions.push({
        id: `c_custom_${Date.now()}`,
        field,
        op,
        value,
        unit: meta.unit,
        window: meta.window,
        confidence: 1,
      })
      this.showAddCondition = false
      this.toast('已添加条件')
      this.schedulePreview()
    },

    setPolicy(policy: string) {
      if (!this.dsl) return
      this.dsl.missing_policy = policy
      this.schedulePreview()
    },

    async screen() {
      if (!this.dsl) return
      this.screenLoading = true
      this.screenError = null
      this.job = null
      try {
        const { job_id } = await api.createScreenJob(this.dsl)
        this.pollJob(job_id)
      } catch (error) {
        const payload = (error as any)?.payload
        this.screenError = {
          message: (error as Error).message,
          hint: payload?.error?.hint || payload?.detail?.hint,
        }
        this.screenLoading = false
        this.toast((error as Error).message || '筛选失败')
      }
    },

    async pollJob(jobId: string) {
      if (pollTimer) clearTimeout(pollTimer)
      try {
        const job = await api.getJob(jobId)
        this.job = job
        if (job.status === 'done' && job.result) {
          this.screenResult = job.result
          this.activeTab = 'included'
          this.screenLoading = false
          this.step = 'results'
          window.scrollTo({ top: 0, behavior: 'smooth' })
          this.toast('筛选完成')
          return
        }
        if (job.status === 'failed') {
          this.screenError = {
            message: job.error?.message || '筛选失败',
            hint: job.error?.hint,
          }
          this.screenLoading = false
          this.toast(job.error?.message || '筛选失败')
          return
        }
        pollTimer = setTimeout(() => this.pollJob(jobId), 900)
      } catch (error) {
        this.screenError = { message: (error as Error).message }
        this.screenLoading = false
        this.toast((error as Error).message || '获取筛选进度失败')
      }
    },

    cancelScreen() {
      if (pollTimer) clearTimeout(pollTimer)
      this.screenLoading = false
      this.toast('已停止等待；后台任务可能仍在运行')
    },

    async diagnose(query: string) {
      if (!this.dsl) return
      this.diagnoseLoading = true
      try {
        const { stock } = await api.diagnose(query, this.dsl)
        this.openDrawer(stock)
      } catch (error) {
        this.toast((error as Error).message || '诊断失败')
      } finally {
        this.diagnoseLoading = false
      }
    },

    openDrawer(stock: StockResult) {
      this.drawerStock = stock
      this.drawerOpen = true
      this.explanation = null
    },

    closeDrawer() {
      this.drawerOpen = false
      this.drawerStock = null
      this.explanation = null
    },

    async explainCurrent() {
      if (!this.drawerStock || !this.dsl) return
      this.explainLoading = true
      try {
        const { explanation } = await api.explain(this.drawerStock.thscode, this.dsl)
        this.explanation = explanation
      } catch (error) {
        this.toast((error as Error).message || '解读失败')
      } finally {
        this.explainLoading = false
      }
    },

    toggleCompare(stock: StockResult) {
      const index = this.compareStocks.findIndex((item) => item.thscode === stock.thscode)
      if (index >= 0) {
        this.compareStocks.splice(index, 1)
        return
      }
      if (this.compareStocks.length >= 3) {
        this.toast('最多对比 3 只股票')
        return
      }
      this.compareStocks.push(stock)
      this.toast(`已加入对比（${this.compareStocks.length}/3）`)
    },

    openCompare() {
      if (this.compareStocks.length < 2) {
        this.toast('至少选择 2 只股票')
        return
      }
      this.showCompare = true
    },

    clearCompare() {
      this.compareStocks = []
      this.showCompare = false
    },

    async loadStrategies() {
      this.strategiesLoading = true
      try {
        const { items } = await api.listStrategies()
        this.strategies = items
      } catch (error) {
        this.toast((error as Error).message || '加载策略失败')
      } finally {
        this.strategiesLoading = false
      }
    },

    async saveStrategy(name: string, monitor: boolean) {
      if (!this.dsl) return
      try {
        await api.createStrategy({
          name,
          query: this.query,
          dsl: this.dsl,
          monitor_enabled: monitor,
        })
        this.toast(monitor ? '监控已创建，每日 18:30 自动检查' : '策略已保存')
        await this.loadStrategies()
        if (monitor) this.showStrategies = true
      } catch (error) {
        this.toast((error as Error).message || '保存失败')
      }
    },

    async runStrategy(id: string) {
      try {
        const result = await api.runStrategy(id)
        this.strategyResult = result
        this.toast(
          `检查完成：新进 ${result?.diff?.new?.length ?? 0} 只，退出 ${result?.diff?.exit?.length ?? 0} 只`,
        )
        await this.loadStrategies()
      } catch (error) {
        this.toast((error as Error).message || '检查失败')
      }
    },

    reset() {
      this.step = 'intent'
      this.parseResult = null
      this.dsl = null
      this.preview = null
      this.baselineSummary = null
      this.screenResult = null
      this.job = null
      this.screenError = null
      this.compareStocks = []
      this.closeDrawer()
      window.scrollTo({ top: 0, behavior: 'smooth' })
    },
  },
})
