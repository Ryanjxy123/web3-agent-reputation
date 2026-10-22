<script setup lang="ts">
import { externalLink } from '../format'

const props = defineProps<{ sources: string[]; reportId?: string; agentKey?: string }>()

function downloadLink(source: string): string | undefined {
  if (!source.startsWith('runtime/')) return undefined
  if (props.reportId) return '/api/reports/' + encodeURIComponent(props.reportId) + '/evidence?path=' + encodeURIComponent(source)
  if (props.agentKey) return '/api/agents/' + encodeURIComponent(props.agentKey) + '/chain-evidence/file?path=' + encodeURIComponent(source)
  return undefined
}
</script>

<template>
  <ul v-if="sources.length" class="evidence-list">
    <li v-for="(source, index) in sources" :key="index">
      <a v-if="externalLink(source)" :href="externalLink(source)" target="_blank" rel="noopener noreferrer">{{ source }}<span class="sr-only">（新窗口打开）</span></a>
      <a v-else-if="downloadLink(source)" :href="downloadLink(source)" download>{{ source }}<span class="sr-only">（下载本次核验引用的原始证据）</span></a>
      <code v-else>{{ source }}</code>
    </li>
  </ul>
  <p v-else class="muted">本项没有记录原始证据位置。</p>
</template>
