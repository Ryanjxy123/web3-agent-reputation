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
    <p class="score-counts"><span>通过 <b>{{ dimension.passed }}</b><small>PASS</small></span><span>未通过 <b>{{ dimension.failed }}</b><small>FAIL</small></span><span>无法判断 <b>{{ dimension.unknown }}</b><small>UNKNOWN</small></span><span>不适用 <b>{{ dimension.not_applicable }}</b><small>N_A</small></span></p>
    <p class="muted small">已保留 {{ dimension.observed }} / {{ dimension.planned }} 个计划样本<br>判分分母 {{ dimension.passed + dimension.failed }} 个确定结论</p>
    <p v-if="dimension.value === null" class="score-gap">{{ dimension.observed === 0 ? '尚无本维度任务样本。' : '样本或确定结论尚未达到政策门槛，具体原因见任务与缺项。' }}待评价不计为 0 分。</p>
  </article>
</template>
