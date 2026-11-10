<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'

// One visibility gate for CSS motion throughout the app; no perpetual JS frame loop.
const visible = ref(!document.hidden)
function visibility() {
  visible.value = !document.hidden
  document.documentElement.classList.toggle('motion-paused', !visible.value)
}
onMounted(() => { visibility(); document.addEventListener('visibilitychange', visibility) })
onBeforeUnmount(() => {
  document.removeEventListener('visibilitychange', visibility)
  document.documentElement.classList.remove('motion-paused')
})
defineProps<{ quiet: boolean }>()
</script>

<template>
  <div class="spatial-backdrop" :class="{ quiet, suspended: !visible }" aria-hidden="true">
    <div class="ambient-light ambient-cyan"></div><div class="ambient-light ambient-violet"></div>
    <svg class="space-lattice" viewBox="0 0 1600 1000" preserveAspectRatio="xMidYMid slice" fill="none">
      <defs><linearGradient id="space-fade" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#578398" stop-opacity="0"/><stop offset=".5" stop-color="#5687a3" stop-opacity=".24"/><stop offset="1" stop-color="#677c9b" stop-opacity=".04"/></linearGradient></defs>
      <g stroke="url(#space-fade)" stroke-width=".7">
        <path v-for="i in 18" :key="'ray'+i" :d="`M ${400+i*42} 230 L ${-900+i*190} 1000`" />
        <path v-for="y in [370,410,460,525,610,720,865]" :key="y" :d="`M 0 ${y} Q 800 ${y-90} 1600 ${y}`" />
      </g>
      <g stroke="#83a4cf" stroke-opacity=".12" stroke-width=".8">
        <path d="M1080 75 1420 250 1250 480 950 310Z M1080 75 1250 480M1420 250 950 310M1250 480 1515 660 1350 880M950 310 750 540 1090 710 1250 480"/>
        <path d="M60 130 350 220 160 440 380 615 120 800M60 130 160 440M350 220 380 615M160 440 120 800"/>
      </g>
      <g fill="#99c8e9" opacity=".3"><circle v-for="p in [[1080,75],[1420,250],[1250,480],[950,310],[750,540],[1090,710],[350,220],[160,440],[380,615]]" :key="p.join()" :cx="p[0]" :cy="p[1]" r="2"/></g>
      <circle class="space-packet" r="2.5" fill="#77d8e4" style="offset-path:path('M1080 75 L1420 250 L1250 480 L950 310');"/>
      <circle class="space-packet second" r="2" fill="#a6a0e8" style="offset-path:path('M60 130 L350 220 L160 440 L380 615');"/>
    </svg>
  </div>
</template>
