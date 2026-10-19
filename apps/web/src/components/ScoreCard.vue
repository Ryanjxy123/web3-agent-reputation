<script setup lang="ts">
import type { DimensionScore } from '../contracts'
import { score } from '../format'

defineProps<{ title: string; weight: string; dimension: DimensionScore }>()
</script>

<template>
  <article class="score-card">
    <div class="row-between"><h3>{{ title }}</h3><span class="muted small">权重 {{ weight }}</span></div>
    <p class="dimension-value" :class="{ pending: dimension.value === null }">{{ score(dimension.value) }}<span v-if="dimension.value !== null"> / 100</span></p>
    <div v-if="dimension.value !== null" class="score-track" aria-hidden="true"><span :style="{ width: dimension.value + '%' }"></span></div>
    <p class="score-counts"><span>通过 <b>{{ dimension.passed }}</b></span><span>未通过 <b>{{ dimension.failed }}</b></span><span>无法判断 <b>{{ dimension.unknown }}</b></span><span>不适用 <b>{{ dimension.not_applicable }}</b></span></p>
    <p class="muted small">已保留 {{ dimension.observed }} / {{ dimension.planned }} 个计划样本<br>判分分母 {{ dimension.passed + dimension.failed }} 个确定结论</p>
  </article>
</template>
