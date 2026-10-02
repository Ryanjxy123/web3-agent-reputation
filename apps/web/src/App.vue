<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { checkConnection, type Connection } from './status';
const connection = ref<Connection>('checking');
const labels: Record<Connection, string> = { checking: '正在连接平台', connected: '平台进程已连接', unavailable: '平台尚未连接' };
async function refresh() { connection.value = 'checking'; connection.value = await checkConnection(); }
onMounted(refresh);
</script>

<template>
  <main>
    <p class="eyebrow">LOCAL DEMO · 本地测试链</p>
    <h1>Web3 Agent 证据评价</h1>
    <p>从声明、任务到链上业务结果，检查一笔成功交易是否属于当前任务。</p>
    <section aria-live="polite">
      <h2>{{ labels[connection] }}</h2>
      <p>连接状态只表示平台进程可达。Agent 的任务结果以独立核验后的证据报告为准。</p>
      <button :disabled="connection === 'checking'" @click="refresh">重新检查连接</button>
    </section>
    <p class="note">工程基线正在建设，尚未产生测评报告。</p>
  </main>
</template>

<style>
:root { font-family: system-ui, sans-serif; color: #192d35; background: #f2f5f4; }
body { margin: 0; }
main { max-width: 840px; margin: 10vh auto; padding: 24px; }
h1 { font-size: clamp(28px, 5vw, 44px); }
p { line-height: 1.8; }
.eyebrow, .note { color: #536b72; }
section { background: white; border: 1px solid #cbd8d8; padding: 28px; margin: 32px 0; border-radius: 12px; }
button { padding: 10px 18px; background: #165f61; color: white; border: 0; border-radius: 6px; cursor: pointer; }
button:disabled { opacity: .6; cursor: wait; }
</style>
