import assert from 'node:assert/strict'
import test from 'node:test'
import { layoutTrace, NODE_WIDTH, NODE_HEIGHT } from '../src/traceLayout.ts'

const node = (id, lane='execution') => ({id,lane,status:'PASS'})
const edge = (from,to,kind='execution') => ({id:from+to,from,to,kind})
const fixture = (count) => {
  const execution=Array.from({length:count},(_,i)=>node('step'+i))
  return {nodes:[...execution,{...node('service'),status:'unrecorded'},node('verification','verification'),node('criteria','verification')],edges:[...execution.slice(1).map((n,i)=>edge('step'+i,n.id)),edge('step'+(count-1),'verification','evidence'),edge('verification','criteria','evidence')]}
}

test('realistic simple, long, and branching traces fit without node overlap at all desktop widths',()=>{
  for(const width of [700,840,1200])for(const count of [2,4,10,18]){
    const trace=fixture(count),before=JSON.stringify(trace)
    const layout=layoutTrace(trace,width),points=[...layout.positions.values()]
    assert.equal(layout.positions.size,trace.nodes.length)
    for(const a of points){
      assert.ok(a.x>=0&&a.x+NODE_WIDTH<=layout.width)
      assert.ok(a.y>=0&&a.y+NODE_HEIGHT<=layout.height)
      for(const b of points)if(a!==b)assert.ok(a.x+NODE_WIDTH<=b.x||b.x+NODE_WIDTH<=a.x||a.y+NODE_HEIGHT<=b.y||b.y+NODE_HEIGHT<=a.y)
    }
    for(const e of [...trace.edges,edge('step0','step'+(count-1)),edge('step0','verification','evidence')]){
      assert.match(layout.path(e),/^M /)
      assert.ok(!/NaN|undefined/.test(layout.path(e)))
    }
    assert.equal(JSON.stringify(trace),before)
  }
})

test('simple trace is one row at 840px; missing service is parked without inventing edges',()=>{
  const trace=fixture(4),layout=layoutTrace(trace,840)
  assert.equal(new Set(['step0','step1','step2','step3'].map(id=>layout.positions.get(id).y)).size,1)
  assert.equal(layout.positions.get('service').y,layout.positions.get('verification').y)
  assert.equal(trace.edges.some(e=>e.from==='service'||e.to==='service'),false)
  const isolatedTask={nodes:[node('task'),node('result'),node('verification','verification'),node('criteria','verification')],edges:[edge('result','verification','evidence'),edge('verification','criteria','evidence')]}
  assert.equal(layoutTrace(isolatedTask,700).positions.get('task').y,48)
})
