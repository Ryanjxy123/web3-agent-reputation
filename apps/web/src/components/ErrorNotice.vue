<script setup lang="ts">
import type { ApiError } from '../api'

defineProps<{ error: ApiError }>()
</script>

<template><section class="error-notice" role="alert"><p>{{ error.message }}</p><slot /><details v-if="error.detail"><summary>技术详情</summary><pre>{{ error.detail }}</pre></details></section></template>
