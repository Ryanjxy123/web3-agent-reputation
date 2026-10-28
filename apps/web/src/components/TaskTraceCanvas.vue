<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, useId, watch } from 'vue'
import type { TaskTraceViewModel, TraceNode, TraceEdge } from '../traceProjection'
import { layoutTrace, NODE_WIDTH, NODE_HEIGHT } from '../traceLayout'
import '../trace-canvas.css'
const props = defineProps<{
  trace: TaskTraceViewModel; selectedId: string; playing: boolean
  transitId: string; arrivedId: string; visited: string[]; signalVersion: number; transitMs: number
}>()
const emit = defineEmits<{ select: [id: string] }>()
const instance = useId().replace(/:/g, '')
const zoom = ref(1)
const available = ref(800)
const viewport = ref<HTMLElement | null>(null)
const hovered = ref('')
const feedback = ref('')
let feedbackTimer: ReturnType<typeof setTimeout> | undefined
let observer: ResizeObserver | undefined
const layout = computed(() => layoutTrace(props.trace, available.value))
const focusId = computed(() => props.transitId || hovered.value || props.selectedId)
const activeEdges = computed(() => new Set(props.trace.edges.filter(e => e.from === focusId.value || e.to === focusId.value).map(e => e.id)))
const signalEdges = computed(() => props.trace.edges.filter(e => e.to === props.transitId))
const visitedSet = computed(() => new Set(props.visited))
const relatedNodes = computed(() => new Set(props.trace.edges.filter(e => activeEdges.value.has(e.id)).flatMap(e => [e.from,e.to])))
function tone(edge: TraceEdge) {
  const target=props.trace.nodes.find(n=>n.id===edge.to)
  if(target && ['UNKNOWN','invalid','unrecorded','NOT_APPLICABLE'].includes(target.status)) return 'neutral'
  return edge.kind==='evidence'?'evidence':target?.action?'chain':'request'
}
function measure() {
  available.value=Math.max(700,(viewport.value?.clientWidth??800)-2)
}
function fit(notify=false) {
  measure()
  zoom.value=Math.min(1,(viewport.value?.clientWidth??800)/layout.value.width)
  if(notify){zoom.value=Math.min(zoom.value,(viewport.value?.clientHeight??layout.value.height)/layout.value.height);announce('已适应画布')}
}
function announce(message:string) {
  if(feedbackTimer)clearTimeout(feedbackTimer)
  feedback.value=message
  feedbackTimer=setTimeout(()=>{feedback.value=''},1600)
}
function reset(){zoom.value=1;viewport.value?.scrollTo({top:0,left:0});announce('视图已重置')}
function symbol(node:TraceNode){
  if(node.id==='verification')return 'm12 3 8 4v5c0 5-8 9-8 9S4 17 4 12V7l8-4Z M8 12l3 3 5-6'
  if(node.id==='criteria')return 'M6 3h12v18H6z M9 8h6M9 12h6M9 16h4'
  if(node.id==='wallet')return 'M4 6h16v14H4z M4 6V3h12v3 M14 11h6v5h-6z'
  if(node.action?.action==='contract_read')return 'M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z M9 12a3 3 0 1 0 6 0a3 3 0 1 0-6 0'
  if(node.action)return 'm8 6-6 6 6 6m8-12 6 6-6 6m-3-15-2 18'
  if(node.id==='service'||node.id==='response')return 'M5 6h14v12H5z M9 10h.1M15 10h.1 M9 14h6M12 3v3M2 10h3m14 0h3'
  if(node.id==='task')return 'M6 3h9l4 4v14H6z M14 3v5h5M9 12h7M9 16h5'
  return 'm12 3 8 5v8l-8 5-8-5V8l8-5ZM4 8l8 5 8-5M12 13v8'
}
watch(()=>props.trace.taskKey,()=>{hovered.value='';viewport.value?.scrollTo({top:0,left:0})})
watch(()=>props.selectedId,async()=>{
  if(!props.playing)return
  await nextTick()
  const p=layout.value.positions.get(props.selectedId),el=viewport.value
  if(!p||!el)return
  const top=p.y*zoom.value,bottom=(p.y+NODE_HEIGHT)*zoom.value
  if(top<el.scrollTop||bottom>el.scrollTop+el.clientHeight)el.scrollTo({top:Math.max(0,top-60),behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'})
})
onMounted(()=>{fit();observer=new ResizeObserver(measure);if(viewport.value)observer.observe(viewport.value)})
onBeforeUnmount(()=>{observer?.disconnect();if(feedbackTimer)clearTimeout(feedbackTimer)})
</script>
<template>
  <section class="trace-canvas" :class="{'is-playing':playing}" aria-label="任务执行与核验关系图">
    <header class="canvas-toolbar"><span><i></i>执行拓扑 <small>EXECUTION TRACE</small></span><div class="canvas-tools"><button aria-label="缩小关系图" :disabled="zoom<=.6" @click="zoom=Math.max(.6,zoom-.1)">−</button><span>{{ Math.round(zoom*100) }}%</span><button aria-label="放大关系图" :disabled="zoom>=1.4" @click="zoom=Math.min(1.4,zoom+.1)">+</button><button @click="fit(true)">适应视图</button><button @click="reset">重置</button></div></header>
    <div ref="viewport" class="canvas-viewport">
      <div class="canvas-size" :style="{width:layout.width*zoom+'px',height:layout.height*zoom+'px'}">
        <div :key="trace.taskKey" class="graph-surface" :style="{width:layout.width+'px',height:layout.height+'px',transform:`scale(${zoom})`}">
          <span class="lane-label"><b>01</b> 业务执行 <small>按已有记录连接</small></span>
          <div class="verification-plane" :style="{top:layout.laneY+'px'}"></div>
          <span class="lane-label verification-label" :style="{top:layout.laneY+8+'px'}"><b>02</b> 证据与独立核验 <small v-if="trace.nodes.some(n=>n.status==='unrecorded')">未记录环节单列</small></span>
          <svg class="graph-edges" :viewBox="`0 0 ${layout.width} ${layout.height}`" aria-hidden="true">
            <defs><marker :id="instance+'-arrow'" markerWidth="7" markerHeight="7" refX="5" refY="3.5" orient="auto-start-reverse"><path d="M1,1 L5,3.5 L1,6" fill="none" stroke="#809eaf" stroke-width="1"/></marker></defs>
            <g v-for="edge in trace.edges" :key="edge.id" :class="['edge-group',tone(edge),{active:activeEdges.has(edge.id),traversed:visitedSet.has(edge.from)&&visitedSet.has(edge.to),transmitting:edge.to===transitId}]">
              <path class="edge-aura" :d="layout.path(edge)"/><path :class="['trace-edge',edge.kind]" :d="layout.path(edge)" :marker-end="`url(#${instance}-arrow)`"/>
              <text v-if="activeEdges.has(edge.id)&&layout.positions.get(edge.from)?.y===layout.positions.get(edge.to)?.y" class="edge-label" :x="((layout.positions.get(edge.from)?.x??0)+(layout.positions.get(edge.to)?.x??0)+NODE_WIDTH)/2" :y="(layout.positions.get(edge.from)?.y??0)+NODE_HEIGHT/2-10" text-anchor="middle">{{ edge.kind==='evidence'?'证据':edge.label==='同笔后续调用'?'调用':'请求' }}</text>
            </g>
            <g v-for="edge in signalEdges" :key="edge.id+':'+signalVersion" :class="['signal-group',tone(edge)]" :style="{'--signal-path':`path('${layout.path(edge)}')`,'--transit':transitMs+'ms'}"><circle class="trace-signal signal-halo" r="7"/><circle class="trace-signal signal-core" r="2.8"/></g>
          </svg>
          <button v-for="(node,index) in trace.nodes" :key="node.id" :data-node-id="node.id" :class="['graph-node',node.lane,'status-'+node.status,'tone-'+node.tone,{selected:node.id===selectedId,related:relatedNodes.has(node.id),visited:visitedSet.has(node.id),receiving:node.id===transitId,arrived:node.id===arrivedId,contract:!!node.action}]" :style="{left:layout.positions.get(node.id)?.x+'px',top:layout.positions.get(node.id)?.y+'px',width:NODE_WIDTH+'px',height:NODE_HEIGHT+'px'}" :aria-pressed="node.id===selectedId" @mouseenter="hovered=node.id" @mouseleave="hovered=''" @focus="hovered=node.id" @blur="hovered=''" @click="emit('select',node.id)">
            <span class="node-top"><span class="node-symbol"><svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path :d="symbol(node)"/></svg></span><span class="node-kind">{{ node.role }}</span><span class="node-number">{{ String(index+1).padStart(2,'0') }}</span></span>
            <strong>{{ node.title }}</strong><span class="node-summary">{{ node.summary }}</span>
            <span class="node-bottom"><span class="node-visited">{{ node.id===transitId?'正在进入':node.id===selectedId?'当前步骤':visitedSet.has(node.id)?'已回放':'' }}</span><span class="node-verdict"><i>{{ node.tone==='danger'?'×':node.status==='unrecorded'?'—':'·' }}</i>{{ node.statusLabel }}</span></span>
          </button>
        </div>
      </div>
    </div>
    <footer class="canvas-legend"><span><i class="solid"></i>执行关系</span><span><i class="dashed"></i>证据关系</span><span><i class="chain"></i>链上调用</span><span class="canvas-feedback" role="status">{{ feedback||'选择节点，检查来源证据' }}</span></footer>
  </section>
</template>
