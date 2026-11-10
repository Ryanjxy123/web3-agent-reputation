import type { TaskTraceViewModel, TraceEdge } from './traceProjection'

export const NODE_WIDTH = 176
export const NODE_HEIGHT = 116
type Point = { x: number; y: number }

/** Display geometry only. Missing observations remain disconnected from execution. */
export function layoutTrace(trace: TaskTraceViewModel, available: number) {
  const width = Math.max(700, Math.round(available))
  const columns = Math.max(3, Math.min(5, Math.floor((width - 24) / (NODE_WIDTH + 24))))
  const stride = (width - 48 - NODE_WIDTH) / (columns - 1)
  const isolated = (id: string) => id === 'service' && !trace.edges.some(e => e.from === id || e.to === id)
  const execution = trace.nodes.filter(n => n.lane === 'execution' && !isolated(n.id))
  const supporting = trace.nodes.filter(n => n.lane === 'verification' || isolated(n.id))
  const rows = Math.ceil(execution.length / columns)
  const laneY = 48 + rows * 156 + 8
  const positions = new Map<string, Point>()
  execution.forEach((node, i) => {
    const row = Math.floor(i / columns)
    const column = row % 2 ? columns - 1 - i % columns : i % columns
    positions.set(node.id, { x: 24 + column * stride, y: 48 + row * 156 })
  })
  supporting.forEach((node, i) => positions.set(node.id, {
    x: 24 + (supporting.length === 1 ? 0 : i * (width - 48 - NODE_WIDTH) / (supporting.length - 1)), y: laneY + 38,
  }))
  function path(edge: TraceEdge) {
    const a = positions.get(edge.from), b = positions.get(edge.to)
    if (!a || !b) return ''
    const w = NODE_WIDTH, h = NODE_HEIGHT
    if (a.y === b.y) {
      const right = b.x > a.x
      const intervening = [...positions.values()].some(p => p !== a && p !== b && p.y === a.y && p.x > Math.min(a.x,b.x) && p.x < Math.max(a.x,b.x))
      if (!intervening) {
        const start=a.x+(right?w:0), end=b.x+(right?-7:w+7)
        return `M ${start} ${a.y+h/2} C ${(start+end)/2} ${a.y+h/2}, ${(start+end)/2} ${b.y+h/2}, ${end} ${b.y+h/2}`
      }
      return rounded([{x:a.x+w/2,y:a.y},{x:a.x+w/2,y:a.y-18},{x:b.x+w/2,y:b.y-18},{x:b.x+w/2,y:b.y-7}])
    }
    if (Math.abs(a.x-b.x)<1 && b.y-a.y<=156) return `M ${a.x+w/2} ${a.y+h} L ${b.x+w/2} ${b.y-7}`
    const channel=a.y+h+23
    if (b.y-a.y>156) {
      const rail=a.x+w/2<width/2?13:width-13
      return rounded([{x:a.x+w/2,y:a.y+h},{x:a.x+w/2,y:channel},{x:rail,y:channel},{x:rail,y:b.y-18},{x:b.x+w/2,y:b.y-18},{x:b.x+w/2,y:b.y-7}])
    }
    return rounded([{x:a.x+w/2,y:a.y+h},{x:a.x+w/2,y:channel},{x:b.x+w/2,y:channel},{x:b.x+w/2,y:b.y-7}])
  }
  return {width,height:laneY+38+NODE_HEIGHT+26,laneY,positions,path}
}

function rounded(points: Point[]) {
  let d=`M ${points[0]!.x} ${points[0]!.y}`
  for (let i=1;i<points.length-1;i++) {
    const a=points[i-1]!,b=points[i]!,c=points[i+1]!
    const before=Math.hypot(b.x-a.x,b.y-a.y),after=Math.hypot(c.x-b.x,c.y-b.y)
    const r=Math.min(10,before/2,after/2)
    if (!before || !after) continue
    d+=` L ${b.x+(a.x-b.x)*r/before} ${b.y+(a.y-b.y)*r/before} Q ${b.x} ${b.y} ${b.x+(c.x-b.x)*r/after} ${b.y+(c.y-b.y)*r/after}`
  }
  return d+` L ${points.at(-1)!.x} ${points.at(-1)!.y}`
}
