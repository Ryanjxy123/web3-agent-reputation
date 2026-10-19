<script setup lang="ts">
import type { Verdict } from '../contracts'
import { verdictLabel } from '../format'

defineProps<{ verdict: Verdict }>()
</script>

<template><span class="badge" :class="'verdict-' + verdict.toLowerCase()">{{ verdictLabel[verdict] }}</span></template>
