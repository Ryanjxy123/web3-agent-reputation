<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { AgentSummary, EvaluationReport, MeasurementPurpose, ReportChainEvidence } from '../contracts'
import { getReportChainEvidence } from '../api'
import { businessText, criterionTitles, isAssetLabelNotice, loadTraceSources, projectTaskTrace, projectTaskTraces } from '../traceProjection'
import type { TraceSourceRecord } from '../traceProjection'
import { when } from '../format'
import { chainName } from '../agentProfile'
import EvidenceList from './EvidenceList.vue'
import StatusBadge from './StatusBadge.vue'
import TaskTraceCanvas from './TaskTraceCanvas.vue'
import TraceInspector from './TraceInspector.vue'
import '../trace-workbench.css'
const props=defineProps<{agent:AgentSummary;report:EvaluationReport;reportId:string;initialTaskKey?:string;initialDimension?:string}>()
const emit=defineEmits<{report:[taskKey:string,dimension?:MeasurementPurpose]}>()
const baseTraces=computed(()=>projectTaskTraces(props.reportId,props.report))
const selectedKey=ref('')
const selectedId=ref('task')
const search=ref('')
const capability=ref('all')
const outcome=ref('all')
const dimension=ref(props.initialDimension||'all')
const detailTab=ref<'steps'|'criteria'|'evidence'>(props.initialDimension?'criteria':'steps')
const sources=ref<TraceSourceRecord[]>([])
const chain=ref<ReportChainEvidence|null>(null)
const loading=ref(false)
const chainError=ref(false)
const sourceError=computed(()=>sources.value.filter(s=>s.error))
const playing=ref(false)
const transitId=ref('')
const arrivedId=ref('')
const visited=ref<string[]>([])
const signalVersion=ref(0)
const replayComplete=ref(false)
const transitMs=900
const holdMs=1100
const drawer=ref(false)
const narrow=ref(false)
const inspectorShell=ref<HTMLElement|null>(null)
const taskIndex=ref<HTMLElement|null>(null)
const detailOpen=ref(!!props.initialDimension)
let returnFocus:HTMLElement|null=null
let timer:ReturnType<typeof setTimeout>|undefined
let abort:AbortController|undefined
let generation=0
let requestedNode = new URLSearchParams(location.search).get('node')
const cache=new Map<string,{chain:ReportChainEvidence|null;sources:TraceSourceRecord[];chainError:boolean}>()
const media=window.matchMedia('(max-width: 1279px)')
const trace=computed(()=>projectTaskTrace(props.reportId,props.report,selectedKey.value,chain.value,sources.value))
const selectedNode=computed(()=>trace.value?.nodes.find(n=>n.id===selectedId.value)??trace.value?.nodes[0]??null)
const currentIndex=computed(()=>trace.value?.steps.findIndex(s=>s.nodeId===selectedNode.value?.id)??-1)
const uniqueTransactions=computed(()=>new Set(trace.value?.nodes.flatMap(n=>n.action?[n.action.transaction_hash]:[])??[]).size)
const capabilities=computed(()=>props.report.shared_assessment?.capabilities.filter(c=>c.selected)??[])
const shown=computed(()=>baseTraces.value.filter(t=>(!search.value||[t.title,t.taskKey,t.capabilityTitle,t.requestSummary,t.resultSummary,...t.samples.flatMap(s=>[s.title,s.input_summary])].join(' ').toLowerCase().includes(search.value.toLowerCase()))&&(capability.value==='all'||t.capabilityId===capability.value)&&(outcome.value==='all'||outcome.value==='issues'&&t.hasIssues||t.outcome===outcome.value)&&(dimension.value==='all'||t.observations.some(o=>o.dimension===dimension.value))))
const observations=computed(()=>trace.value?.observations.filter(o=>dimension.value==='all'||o.dimension===dimension.value)??[])
const attentionChecks=computed(()=>observations.value.filter(o=>o.measurement_validity!=='valid'||o.verdict==='FAIL'||o.verdict==='UNKNOWN'))
const routineChecks=computed(()=>observations.value.filter(o=>o.measurement_validity==='valid'&&o.verdict!=='FAIL'&&o.verdict!=='UNKNOWN'))
const checkCounts=computed(()=>({passed:observations.value.filter(o=>o.measurement_validity==='valid'&&o.verdict==='PASS').length,failed:observations.value.filter(o=>o.measurement_validity==='valid'&&o.verdict==='FAIL'&&!isAssetLabelNotice(o)).length,notices:observations.value.filter(isAssetLabelNotice).length,unknown:observations.value.filter(o=>o.measurement_validity!=='valid'||o.verdict==='UNKNOWN').length}))
const checkGroups=computed(()=>[{title:'需要关注',items:attentionChecks.value,attention:true},{title:'通过及不适用项目',items:routineChecks.value,attention:false}].filter(group=>group.items.length))
const missingChecks=computed(()=>props.report.shared_assessment?.cases.filter(c=>c.task_keys.includes(selectedKey.value)&&(dimension.value==='all'||c.dimension===dimension.value)).flatMap(c=>{
  const observed=trace.value?.observations.filter(o=>o.case_id===c.case_id)??[]
  const missing=c.criterion_ids.filter(id=>!observed.some(o=>o.criterion_id===id))
  return missing.length?missing.map(id=>({key:c.case_id+id,title:criterionTitles[id]||c.title,dimension:c.dimension})):!observed.length?[{key:c.case_id,title:c.title,dimension:c.dimension}]:[]
})??[])
const taskNetworks=computed(()=>[...new Set(trace.value?.nodes.flatMap(n=>n.action?[chainName(n.action.chain_id)]:[])??[])].join(' · '))
const dimensions:Record<string,string>={availability:'A · 服务可用性',functional:'F · 功能声明一致性',behavioral:'B · 交易行为可靠性'}
function alignTaskSelection(){
  const list=taskIndex.value, item=list?.querySelector<HTMLElement>('.task-option.selected')
  if(!list||!item)return
  if(window.innerWidth<=720)list.scrollLeft=item.offsetLeft-list.offsetLeft-12
  else list.scrollTop=item.offsetTop-list.offsetTop-12
}
watch([selectedKey,selectedId],()=>{inspectorShell.value?.scrollTo({top:0})})
watch([selectedKey,shown],()=>{void nextTick(alignTaskSelection)})
function pause(){
  if(timer!==undefined)clearTimeout(timer)
  timer=undefined;playing.value=false;transitId.value='';arrivedId.value=''
}
function syncUrl(){const query=new URLSearchParams(location.search);query.set('report',props.reportId);query.set('task',selectedKey.value);query.set('node',selectedId.value);history.replaceState(null,'',location.pathname+'?'+query)}
function visit(id:string){
  selectedId.value=id
  if(!visited.value.includes(id))visited.value=[...visited.value,id]
  arrivedId.value=id
  syncUrl()
}
function selectNode(id:string,inspect=true){
  pause();replayComplete.value=false;visit(id)
  if(inspect&&narrow.value){returnFocus=document.activeElement as HTMLElement;drawer.value=true;void nextTick(()=>inspectorShell.value?.querySelector<HTMLButtonElement>('button')?.focus())}
}
function step(delta:number){
  pause();replayComplete.value=false
  const steps=trace.value?.steps??[]
  const item=steps[Math.max(0,Math.min(steps.length-1,currentIndex.value+delta))]
  if(item)visit(item.nodeId)
}
// A transit and a reading interval form one replay step, unrelated to transaction time.
// Only existing incoming relationships are animated; a missing observation has no signal.
function advance(){
  if(!playing.value)return
  const next=trace.value?.steps[currentIndex.value+1]
  if(!next){pause();replayComplete.value=true;return}
  arrivedId.value='';transitId.value=next.nodeId;signalVersion.value++
  timer=setTimeout(()=>{
    transitId.value='';visit(next.nodeId)
    timer=setTimeout(advance,holdMs)
  },transitMs)
}
function play(){
  if(loading.value)return
  if(playing.value){pause();return}
  const steps=trace.value?.steps??[]
  if(!steps.length)return
  replayComplete.value=false
  if(currentIndex.value>=steps.length-1){visited.value=[];visit(steps[0]!.nodeId)}
  else if(selectedNode.value&&!visited.value.includes(selectedNode.value.id))visited.value=[...visited.value,selectedNode.value.id]
  playing.value=true;advance()
}
function restart(){pause();visited.value=[];const first=trace.value?.steps[0];if(first)visit(first.nodeId);play()}
function closeDrawer(){drawer.value=false;void nextTick(()=>returnFocus?.focus())}
function drawerKeys(event:KeyboardEvent){if(!narrow.value||!drawer.value)return;if(event.key==='Escape'){event.preventDefault();closeDrawer()}if(event.key==='Tab'){const controls=Array.from(inspectorShell.value?.querySelectorAll<HTMLElement>('button:not(:disabled),a[href],summary,select,textarea,input,[tabindex="0"]')??[]).filter(el=>el.getClientRects().length>0);if(!controls.length)return;const first=controls[0]!,last=controls[controls.length-1]!;if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus()}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus()}}}
function visibility(){if(document.hidden)pause()}
function mediaChange(){narrow.value=media.matches;if(!media.matches)drawer.value=false}
async function readTask(){pause();abort?.abort();abort=new AbortController();const signal=abort.signal;const version=++generation;drawer.value=false;const existing=cache.get(selectedKey.value);if(existing){chain.value=existing.chain;sources.value=existing.sources;chainError.value=existing.chainError;loading.value=false;return}chain.value=null;sources.value=[];chainError.value=false;const task=props.report.shared_assessment?.tasks.find(t=>t.task_key===selectedKey.value);if(!task)return;loading.value=true;const result=await Promise.allSettled([getReportChainEvidence(props.reportId,signal,task.task_key),loadTraceSources(props.reportId,task,signal)]);if(signal.aborted||version!==generation)return;const a=result[0],b=result[1];chain.value=a.status==='fulfilled'?a.value:null;chainError.value=a.status==='rejected';sources.value=b.status==='fulfilled'?b.value:[{reportId:props.reportId,taskKey:task.task_key,path:'',error:'任务原件暂时无法读取'}];loading.value=false;pause();if(requestedNode){if(trace.value?.nodes.some(n=>n.id===requestedNode))selectedId.value=requestedNode;requestedNode=null;syncUrl()}cache.set(task.task_key,{chain:chain.value,sources:sources.value,chainError:chainError.value})}
watch(selectedKey,()=>{visited.value=[];replayComplete.value=false;selectedId.value='task';if(!requestedNode)syncUrl();void readTask()})
watch(()=>[props.initialTaskKey,props.initialDimension],()=>{if(props.initialDimension){dimension.value=props.initialDimension;detailTab.value='criteria'}if(props.initialTaskKey&&baseTraces.value.some(t=>t.taskKey===props.initialTaskKey))selectedKey.value=props.initialTaskKey})
onMounted(()=>{mediaChange();media.addEventListener('change',mediaChange);document.addEventListener('visibilitychange',visibility);const requested=props.initialTaskKey;const first=requested&&baseTraces.value.find(t=>t.taskKey===requested)||props.initialDimension&&baseTraces.value.find(t=>t.observations.some(o=>o.dimension===props.initialDimension&&o.verdict==='FAIL'))||baseTraces.value.find(t=>t.outcome==='completed')||baseTraces.value[0];selectedKey.value=first?first.taskKey:'';})
onBeforeUnmount(()=>{pause();abort?.abort();media.removeEventListener('change',mediaChange);document.removeEventListener('visibilitychange',visibility)})
</script>
<template>
  <div v-if="baseTraces.length" class="trace-workbench">
    <header class="trace-heading">
      <div><p class="eyebrow">TASK EVIDENCE WORKBENCH</p><h1>真实任务链路 <span>历史任务 / 证据回放</span></h1></div>
      <p>历史报告<br><small>生成于 {{ when(report.generated_at) }}</small></p>
    </header>
    <div class="workbench-layout">
      <aside class="trace-task-list" aria-label="真实任务列表">
        <header><strong>任务索引</strong><span>{{ shown.length }} / {{ baseTraces.length }}</span></header>
        <div class="task-filters">
          <label><span class="sr-only">搜索任务</span><input v-model="search" type="search" placeholder="搜索业务或任务" /></label>
          <label><span class="sr-only">任务能力</span><select v-model="capability"><option value="all">全部业务能力</option><option v-for="c in capabilities" :key="c.capability_id" :value="c.capability_id">{{ c.title }}</option></select></label>
          <label><span class="sr-only">任务结果</span><select v-model="outcome"><option value="all">全部业务结果</option><option value="completed">已完成 / 撤销退款</option><option value="not_executed">报价 / 方案 / 模拟</option><option value="failed">真实执行失败</option><option value="unknown">结局待核</option><option value="issues">含提示 / 未通过 / 未采</option></select></label>
        </div>
        <div ref="taskIndex" class="task-index">
          <button v-for="(item,index) in shown" :key="item.taskKey" class="task-option" :class="[item.outcome,{selected:item.taskKey===selectedKey}]" :aria-pressed="item.taskKey===selectedKey" @click="selectedKey=item.taskKey">
            <span class="task-option-top"><code>{{ String(index+1).padStart(2,'0') }}</code><span>{{ item.outcomeLabel }}</span></span>
            <strong>{{ item.title }}</strong>
            <span class="task-option-summary">{{ item.resultSummary }}</span>
            <span class="task-option-verification" :class="'verification-'+item.verificationTone">{{ item.verificationLabel }}</span>
          </button>
          <p v-if="!shown.length" class="empty-inline">没有匹配的任务。<button class="text-button" @click="search='';capability='all';outcome='all';dimension='all'">清空条件</button></p>
        </div>
        <footer>业务结果与核验结论分别展示</footer>
      </aside>
      <section v-if="trace" class="trace-main" :aria-busy="loading">
        <header class="selected-task-header">
          <div class="task-business-heading"><span class="eyebrow">{{ trace.capabilityTitle }}<template v-if="taskNetworks"> · {{ taskNetworks }}</template></span><span class="trace-result" :class="trace.outcome">{{ trace.outcomeLabel }}</span></div>
          <h2>{{ trace.title }}</h2>
          <dl class="task-business-summary"><div><dt>用户要求</dt><dd>{{ trace.requestSummary }}</dd></div><div><dt>实际结果</dt><dd>{{ trace.resultSummary }}</dd></div></dl>
          <div class="trace-task-meta"><span class="task-verification" :class="'verification-'+trace.verificationTone">{{ trace.verificationLabel }}</span><span v-if="uniqueTransactions">{{ uniqueTransactions }} 笔账户交易</span><button class="text-button" @click="emit('report',selectedKey)">完整任务与评价 ↗</button><button class="text-button inspect-toggle" @click="returnFocus=$event.currentTarget as HTMLElement;drawer=true;nextTick(()=>inspectorShell?.querySelector<HTMLButtonElement>('button')?.focus())">查看当前步骤 ↗</button></div>
          <p v-if="trace.verificationSummary" class="task-verification-note" :class="'verification-'+trace.verificationTone">{{ trace.verificationSummary }}</p>
        </header>
        <div v-if="loading" class="trace-read-status trace-loading-status" role="status">正在读取任务证据…</div>
        <div v-else-if="chainError||sourceError.length" class="trace-read-status warning" role="status">{{ chainError?'链上操作摘要读取失败。':'' }}{{ sourceError.length?sourceError.length+' 份原件暂不可读。':'' }}报告结局与核验项目仍可查看。<button class="text-button" @click="cache.delete(selectedKey);readTask()">重试</button></div>
        <TaskTraceCanvas :trace="trace" :selected-id="selectedNode?.id??''" :playing="playing" :transit-id="transitId" :arrived-id="arrivedId" :visited="visited" :signal-version="signalVersion" :transit-ms="transitMs" :class="{'trace-loading':loading}" @select="selectNode" />
        <div class="mobile-trace-steps" aria-label="任务纵向步骤"><button v-for="(s,i) in trace.steps" :key="s.id" :aria-pressed="s.nodeId===selectedNode?.id" @click="selectNode(s.nodeId)"><span>{{ String(i+1).padStart(2,'0') }}</span><div><strong>{{ s.label }}</strong><p>{{ s.detail }}</p></div><span>↗</span></button></div>
        <div class="replay-controls" :class="{playing,complete:replayComplete}">
          <div><span class="history-dot"></span><strong>{{ playing?'正在回放':replayComplete?'回放结束 · '+trace.outcomeLabel:'历史任务回放' }}</strong><span>{{ currentIndex+1 }} / {{ trace.steps.length }}</span></div>
          <div class="replay-buttons"><button title="重新播放" aria-label="重新播放" :disabled="loading" @click="restart">↺</button><button aria-label="上一步" :disabled="currentIndex<=0" @click="step(-1)">上一步</button><button class="play-button" :disabled="loading" :aria-pressed="playing" @click="play">{{ playing?'暂停':'播放' }}</button><button aria-label="下一步" :disabled="currentIndex>=trace.steps.length-1" @click="step(1)">下一步</button></div>
          <div class="replay-track" aria-label="回放步骤定位"><button v-for="(s,i) in trace.steps" :key="s.id" :title="s.label" :aria-label="`定位第 ${i+1} 步：${s.label}`" :aria-current="s.nodeId===selectedNode?.id?'step':undefined" :class="{seen:visited.includes(s.nodeId),current:s.nodeId===selectedNode?.id,transit:s.nodeId===transitId}" @click="selectNode(s.nodeId,false)"><span></span></button></div>
          <div v-if="playing&&selectedNode" class="replay-business-caption" aria-live="polite"><strong>{{ selectedNode.title }}</strong><span>{{ selectedNode.summary }}</span></div>
          <p>仅回放已有记录 · 动画时长不代表真实耗时</p>
        </div>
        <section class="trace-details">
          <nav class="trace-detail-tabs" aria-label="任务明细">
            <button :aria-pressed="detailTab==='steps'" @click="detailOpen=detailTab==='steps'?!detailOpen:true;detailTab='steps'">业务步骤 <span>{{ trace.steps.length }}</span></button>
            <button :aria-pressed="detailTab==='criteria'" @click="detailOpen=detailTab==='criteria'?!detailOpen:true;detailTab='criteria'">核验项目 <span>{{ trace.observations.length }}</span></button>
            <button :aria-pressed="detailTab==='evidence'" @click="detailOpen=detailTab==='evidence'?!detailOpen:true;detailTab='evidence'">原始证据</button>
            <button class="collapse-details" :aria-expanded="detailOpen" @click="detailOpen=!detailOpen">{{ detailOpen?'收起':'展开' }}</button>
          </nav>
          <div v-if="detailOpen" class="trace-detail-body">
            <div v-if="detailTab==='steps'" class="trace-step-table"><button v-for="(s,i) in trace.steps" :key="s.id" :class="{selected:s.nodeId===selectedNode?.id}" @click="selectNode(s.nodeId)"><code>{{ String(i+1).padStart(2,'0') }}</code><strong>{{ s.label }}</strong><span>{{ s.detail }}</span><span>查看 ↗</span></button></div>
            <div v-else-if="detailTab==='criteria'" class="trace-criteria">
              <label class="criterion-filter">评价维度 <select v-model="dimension"><option value="all">全部维度</option><option v-for="(label,id) in dimensions" :key="id" :value="id">{{ label }}</option></select></label>
              <p class="criterion-counts"><span>{{ checkCounts.passed }} 项通过</span><span v-if="checkCounts.failed" class="verification-danger">{{ checkCounts.failed }} 项业务未通过</span><span v-if="checkCounts.notices" class="verification-notice">{{ checkCounts.notices }} 项标注提示</span><span :class="{'verification-warning':checkCounts.unknown||missingChecks.length}">{{ checkCounts.unknown }} 项待核<template v-if="missingChecks.length"> · {{ missingChecks.length }} 项未采</template></span></p>
              <div v-if="missingChecks.length" class="criterion-missing"><strong>尚未采集的核验</strong><p v-for="missing in missingChecks" :key="missing.key">{{ dimensions[missing.dimension] }} · {{ missing.title }}</p><span>这些项目无法判断，不计为通过。</span></div>
              <details v-for="group in checkGroups" :key="selectedKey+dimension+group.title" class="criterion-group" :open="group.attention">
                <summary>{{ group.title }} · {{ group.items.length }}</summary>
                <article v-for="o in group.items" :key="o.case_id+o.criterion_id" class="criterion-row">
                  <button class="criterion-select" @click="selectNode('criteria',false)"><span>{{ dimensions[o.dimension] }}</span><strong>{{ criterionTitles[o.criterion_id]||o.criterion_id }}</strong><span v-if="isAssetLabelNotice(o)" class="criterion-note">标注提示</span><StatusBadge v-else-if="o.measurement_validity==='valid'" :verdict="o.verdict"/><span v-else class="report-status">{{ o.measurement_validity==='invalid'?'测量无效':'有效性待核' }}</span></button>
                  <p>{{ businessText(o.reason) }}</p>
                  <div class="criterion-actions"><button class="text-button" @click="selectNode('verification')">查看核验依据 ↗</button><button class="text-button" @click="emit('report',selectedKey,o.dimension)">定位评价维度 →</button><details><summary>查看原始证据</summary><EvidenceList :sources="o.evidence" :report-id="reportId" /></details></div>
                </article>
              </details>
              <p v-if="!observations.length&&!missingChecks.length" class="empty-inline">本任务未安排该维度的核验项目。</p>
            </div>
            <div v-else class="trace-evidence"><p class="muted small">当前任务的完整证据引用。选择步骤后，也可在技术详情中预览原始 JSON。</p><EvidenceList :sources="trace.evidence" :report-id="reportId" /></div>
          </div>
        </section>
        <p class="trace-provenance">链路根据历史证据重建。服务响应、用户账户执行和平台独立核验分别记录；未记录的 Agent 内部调用不作推断。</p>
      </section>
      <div v-if="drawer&&narrow" class="inspector-backdrop" @click="closeDrawer"></div>
      <aside v-if="trace" ref="inspectorShell" class="trace-inspector-shell" :class="{open:drawer}" :role="narrow&&drawer?'dialog':undefined" :aria-modal="narrow&&drawer?true:undefined" :aria-labelledby="narrow&&drawer?'trace-inspector-title':undefined" @keydown="drawerKeys"><TraceInspector :task-key="selectedKey" :node="selectedNode" :report-id="reportId" @close="closeDrawer" /></aside>
    </div>
  </div>
</template>
