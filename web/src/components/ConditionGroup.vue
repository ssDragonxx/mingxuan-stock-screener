<script setup lang="ts">
import type { Condition, FieldMeta, Group } from '../types'
import { opLabel, windowLabel } from '../utils'

const props = defineProps<{
  group: Group
  index: number
  fieldMeta: Record<string, FieldMeta>
}>()

const emit = defineEmits<{
  (event: 'apply-option', groupId: string, optionId: string): void
  (event: 'update-condition', conditionId: string, patch: Partial<Condition>): void
  (event: 'remove-condition', conditionId: string): void
}>()

function metaFor(condition: Condition): FieldMeta {
  return (
    props.fieldMeta[condition.field] || {
      label: condition.field,
      unit: condition.unit || '',
      step: 1,
      ops: ['>=', '<=', '>', '<'],
      source: '',
      frequency: '',
      window: condition.window || 'current',
      desc: '',
    }
  )
}

function conditionLabel(condition: Condition): string {
  if (condition.field === 'pe_ttm' && condition.op === '>' && Number(condition.value) === 0) {
    return 'PE(TTM)（剔除负值）'
  }
  return metaFor(condition).label
}

function onOpChange(condition: Condition, event: Event) {
  emit('update-condition', condition.id, {
    op: (event.target as HTMLSelectElement).value,
  })
}

function onValueInput(condition: Condition, event: Event) {
  const value = Number((event.target as HTMLInputElement).value)
  if (!Number.isFinite(value)) return
  emit('update-condition', condition.id, { value })
}

function onDefinitionChange(event: Event) {
  emit('apply-option', props.group.id, (event.target as HTMLSelectElement).value)
}
</script>

<template>
  <article class="condition-group" :data-group-id="group.id">
    <div class="group-head">
      <span class="group-index">{{ String(index + 1).padStart(2, '0') }}</span>
      <span class="group-title">{{ group.label }}</span>
      <span v-if="group.source_phrase && group.source_phrase !== group.label" class="group-source">
        {{ group.source_phrase }}
      </span>
      <select
        v-if="group.options?.length"
        class="select-sm group-definition"
        :value="group.definition || group.options[0]?.id"
        aria-label="条件口径"
        @change="onDefinitionChange"
      >
        <option v-for="option in group.options" :key="option.id" :value="option.id">
          {{ option.label }}
        </option>
      </select>
    </div>
    <div class="group-body">
      <div
        v-for="condition in group.conditions"
        :key="condition.id"
        class="condition-row"
        :data-cond-id="condition.id"
      >
        <div class="cond-label">{{ conditionLabel(condition) }}</div>
        <div class="cond-control">
          <select
            class="op-select"
            :value="condition.op"
            aria-label="算子"
            @change="onOpChange(condition, $event)"
          >
            <option
              v-for="op in metaFor(condition).ops || ['>=', '<=', '>', '<']"
              :key="op"
              :value="op"
            >
              {{ opLabel(op) }}
            </option>
          </select>
          <input
            class="value-input"
            type="number"
            :value="condition.value"
            :step="metaFor(condition).step ?? 1"
            :min="metaFor(condition).min ?? undefined"
            :max="metaFor(condition).max ?? undefined"
            aria-label="阈值"
            @change="onValueInput(condition, $event)"
          />
          <span class="unit">{{ condition.unit || metaFor(condition).unit }}</span>
        </div>
        <div class="condition-meta">
          <span class="meta-badge">{{ windowLabel(condition.window) }}</span>
          <span class="meta-source">{{ metaFor(condition).source }}</span>
        </div>
        <button
          class="icon-btn remove-cond"
          type="button"
          title="删除条件"
          aria-label="删除条件"
          @click="emit('remove-condition', condition.id)"
        >
          ×
        </button>
      </div>
    </div>
  </article>
</template>
