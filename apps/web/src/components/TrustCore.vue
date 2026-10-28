<script setup lang="ts">
import { useId } from 'vue'
const id = useId().replace(/:/g, '')
</script>

<template>
  <figure class="trust-core" aria-label="Agent、合约、证据与核验的概念空间示意，不代表实时网络">
    <svg viewBox="0 0 440 380" fill="none" role="img" aria-label="悬浮可信执行核心">
      <defs>
        <linearGradient :id="id+'-edge'" x1="120" y1="70" x2="330" y2="280" gradientUnits="userSpaceOnUse"><stop stop-color="#b2f8ff"/><stop offset=".4" stop-color="#5aadd0"/><stop offset="1" stop-color="#8c7fd1"/></linearGradient>
        <linearGradient :id="id+'-face'" x1="160" y1="110" x2="290" y2="240" gradientUnits="userSpaceOnUse"><stop stop-color="#76dbe6" stop-opacity=".15"/><stop offset="1" stop-color="#6c68b4" stop-opacity=".025"/></linearGradient>
        <radialGradient :id="id+'-light'"><stop stop-color="#3ca5c4" stop-opacity=".23"/><stop offset="1" stop-color="#3ca5c4" stop-opacity="0"/></radialGradient>
      </defs>
      <ellipse cx="220" cy="205" rx="198" ry="165" :fill="`url(#${id}-light)`"/>
      <g class="core-ground" stroke="#6ba8c6" stroke-width=".65">
        <path v-for="i in 7" :key="'a'+i" :d="`M ${42+i*24} ${226-i*12} l190 95 M ${42+i*24} ${226+i*12} l190 -95`" opacity=".18"/>
        <path d="m52 231 168-84 168 84-168 84-168-84Z" opacity=".35"/>
        <path d="m92 231 128-64 128 64-128 64-128-64Z" opacity=".3"/>
      </g>
      <g class="core-connection" stroke="#477d9a" stroke-width="1">
        <path d="M72 131 134 161 220 119M359 130 306 158 220 119M83 278 147 243 220 282M359 278 294 245 220 282"/>
      </g>
      <g class="core-float">
        <path d="m220 61 91 52v105l-91 53-91-53V113l91-52Z" :fill="`url(#${id}-face)`" :stroke="`url(#${id}-edge)`" stroke-width="1.2"/>
        <path d="m129 113 91 53 91-53m-91 53v105" :stroke="`url(#${id}-edge)`" stroke-width="1.2"/>
        <path d="m220 85 70 41v79l-70 41-70-41v-79l70-41Z M150 126l70 41 70-41M220 167v79" stroke="#85cfdf" stroke-width=".6" opacity=".28"/>
        <path d="m220 119 42 24v48l-42 25-42-25v-48l42-24Z" fill="#1b4e64" fill-opacity=".35" stroke="#9bd8e8" stroke-width="1"/>
        <path d="m178 143 42 24 42-24m-42 24v49" stroke="#92ccde" opacity=".7"/>
        <path d="m203 153 13 8 23-14" stroke="#cdfaff" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
        <path class="core-scan" d="m129 146 91 53 91-53m-182 0 91-52 91 52" stroke="#a2f3ef" stroke-width="1.3" opacity=".6"/>
        <g fill="#c8f6ff"><circle cx="220" cy="61" r="3"/><circle cx="129" cy="113" r="2"/><circle cx="311" cy="113" r="2"/><circle cx="220" cy="271" r="3"/></g>
      </g>
      <g class="core-satellites" stroke-width="1">
        <path d="m72 111 17 10v20l-17 10-17-10v-20l17-10Z" fill="#132737" stroke="#6aa8bc"/><path d="M66 125h12v12H66z" stroke="#b0dce7"/>
        <path d="m359 110 17 10v20l-17 10-17-10v-20l17-10Z" fill="#202239" stroke="#827bb4"/><path d="m356 124-4 6 4 6m6-12 4 6-4 6" stroke="#c9baf2"/>
        <path d="m83 258 17 10v20l-17 10-17-10v-20l17-10Z" fill="#142534" stroke="#60859f"/><path d="M77 271h12m-12 6h12m-12 6h7" stroke="#bad4e5"/>
        <path d="m359 258 17 10v20l-17 10-17-10v-20l17-10Z" fill="#102c2c" stroke="#508c81"/><path d="m352 277 5 5 9-10" stroke="#a1e1cc"/>
      </g>
      <g font-size="11" font-family="inherit" fill="#b0c1d0" text-anchor="middle"><text x="72" y="99">AGENT 服务</text><text x="359" y="98">链上合约</text><text x="83" y="320">来源证据</text><text x="359" y="320">独立核验</text></g>
      <circle class="core-packet" r="2.6" fill="#b7f0f6" style="offset-path:path('M72 131 L134 161 L220 119');"/>
      <circle class="core-packet alternate" r="2.2" fill="#aea0e2" style="offset-path:path('M220 119 L306 158 L359 130');"/>
      <path d="M190 344h60" stroke="#3e667d"/><text x="220" y="362" text-anchor="middle" fill="#6e8c9e" font-size="9" letter-spacing="2.5">TRUST THROUGH EVIDENCE</text>
    </svg>
    <figcaption>概念示意 <span>· 实际记录见任务链路</span></figcaption>
  </figure>
</template>
