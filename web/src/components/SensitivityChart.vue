<script setup lang="ts">
import { computed } from 'vue'
import type { SensitivityItem } from '../types'

const props = defineProps<{ item: SensitivityItem }>()

const width = 320
const height = 128
const padX = 18
const padTop = 18
const padBottom = 26
const innerWidth = width - padX * 2
const innerHeight = height - padTop - padBottom

const coords = computed(() => {
  const points = props.item.points || []
  const values = points.map((point) => point.included)
  const maxY = Math.max(...values, 1)
  const minY = Math.min(...values, 0)
  const range = Math.max(maxY - minY, 1)
  const stepX = points.length > 1 ? innerWidth / (points.length - 1) : 0
  return points.map((point, index) => ({
    ...point,
    x: padX + stepX * index,
    y: padTop + innerHeight - ((point.included - minY) / range) * innerHeight,
  }))
})

const line = computed(() =>
  coords.value
    .map((coord, index) => `${index === 0 ? 'M' : 'L'}${coord.x.toFixed(1)},${coord.y.toFixed(1)}`)
    .join(' '),
)

const axisLabels = computed(() => {
  const points = props.item.points || []
  return coords.value.filter(
    (_, index) =>
      points.length <= 5 ||
      index === 0 ||
      index === points.length - 1 ||
      index % 2 === 0,
  )
})

function isCurrent(threshold: number): boolean {
  return Number(threshold) === Number(props.item.current)
}
</script>

<template>
  <svg
    class="chart"
    :viewBox="`0 0 ${width} ${height}`"
    role="img"
    :aria-label="`${item.label} 敏感性曲线`"
  >
    <line
      class="chart-axis"
      :x1="padX"
      :y1="height - padBottom"
      :x2="width - padX"
      :y2="height - padBottom"
    ></line>
    <path class="chart-line" :d="line"></path>
    <circle
      v-for="coord in coords"
      :key="`dot-${coord.threshold}`"
      class="chart-dot"
      :class="{ current: isCurrent(coord.threshold) }"
      :cx="coord.x"
      :cy="coord.y"
      :r="isCurrent(coord.threshold) ? 4 : 3"
    ></circle>
    <text
      v-for="coord in coords"
      :key="`val-${coord.threshold}`"
      class="chart-value"
      :x="coord.x"
      :y="coord.y - 8"
      text-anchor="middle"
    >
      {{ coord.included }}
    </text>
    <text
      v-for="coord in axisLabels"
      :key="`label-${coord.threshold}`"
      class="chart-label"
      :x="coord.x"
      :y="height - 8"
      text-anchor="middle"
    >
      {{ coord.threshold }}
    </text>
  </svg>
</template>
