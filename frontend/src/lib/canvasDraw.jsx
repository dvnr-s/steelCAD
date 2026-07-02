/* eslint-disable react-refresh/only-export-components --
 * Shared canvas-draw module: intentionally exports both pure helpers (fitScale,
 * collect, region colours) and small non-interactive Konva sub-shapes. It is a
 * library, not a fast-refreshed component file, so the granularity rule doesn't apply. */
/**
 * Shared draw helpers for the design canvas.
 *
 * Pure geometry/colour helpers and non-interactive Konva sub-shapes used by the
 * editor ([DesignCanvas]). The quotation PDF renders its own equivalent server-side
 * (app/services/diagram.py) so every frame's diagram is deterministic and uniform.
 */
import { Line } from 'react-konva'

export const ACTUAL_SCALE = 60   // "100%" = 60 pixels per foot (true size)
export const MAX_SCALE = 60      // fit cap — small frames don't blow up past true size
export const MIN_SCALE = 8       // fit floor so huge frames stay usable
export const FIT_PAD = 64        // px reserved around the frame for labels + handles

// Pixels-per-foot that fits a frame (w×h ft) inside the available viewport,
// leaving a margin for dimension labels and resize handles.
export function fitScale(frameW, frameH, viewW, viewH, pad = FIT_PAD) {
  const sx = (viewW - 2 * pad) / frameW
  const sy = (viewH - 2 * pad) / frameH
  return Math.max(MIN_SCALE, Math.min(MAX_SCALE, sx, sy))
}

// Collect leaf regions + split descriptors (with parent bounds in feet).
export function collect(region, acc) {
  if (region.isLeaf) {
    acc.regions.push(region)
    return acc
  }
  if (region.split) {
    acc.splits.push({
      id: region.split.id,
      regionId: region.id,
      direction: region.split.direction,
      position: region.split.position,
      x: region.x, y: region.y, w: region.width, h: region.height,
    })
    if (region.overlays?.length) acc.regions.push({ ...region, _branchWithGrill: true })
    for (const child of region.split.children) collect(child, acc)
  }
  return acc
}

export function regionFill(region, selectedId) {
  if (region.id === selectedId) return 'rgba(59,130,246,0.18)'
  const rt = region.regionType
  if (rt === 'shutter') return 'rgba(245,158,11,0.08)'
  if (rt === 'door')    return 'rgba(239,68,68,0.08)'
  if (rt === 'fixed')   return 'rgba(34,197,94,0.06)'
  if (rt === 'louver')  return 'rgba(139,92,246,0.08)'
  return 'rgba(59,130,246,0.04)'
}

export function regionStroke(region, selectedId) {
  if (region.id === selectedId) return '#3b82f6'
  const rt = region.regionType
  if (rt === 'shutter') return '#f59e0b'
  if (rt === 'door')    return '#ef4444'
  if (rt === 'fixed')   return '#22c55e'
  if (rt === 'louver')  return '#8b5cf6'
  return '#30363d'
}

// Standard elevation door symbol: a triangle whose apex sits on the hinge edge
// and base spans the latch edge — instantly reads which side opens.
export function DoorSwing({ region, px, py, scale }) {
  const x = px(region.x), y = py(region.y)
  const w = region.width * scale, h = region.height * scale
  const hingeLeft = (region.doorHand || 'left') !== 'right'
  const apexX = hingeLeft ? x : x + w
  const latchX = hingeLeft ? x + w : x
  const pts = [latchX, y + 4, apexX, y + h / 2, latchX, y + h - 4]
  return <Line points={pts} stroke="rgba(239,68,68,0.55)" strokeWidth={1.25} listening={false} />
}

// Hatched "in the concrete" ground band along the bottom edge of a door frame.
export function ConcreteBase({ frame, px, py }) {
  const x0 = px(0), x1 = px(frame.width), yb = py(frame.height)
  const ticks = []
  for (let gx = x0; gx < x1; gx += 12)
    ticks.push(<Line key={gx} points={[gx, yb, gx + 8, yb + 8]} stroke="rgba(139,124,108,0.55)" strokeWidth={1} listening={false} />)
  return (
    <>
      <Line points={[x0, yb, x1, yb]} stroke="#8b7c6c" strokeWidth={3} listening={false} />
      {ticks}
    </>
  )
}

// Faint diagonal hatch marking an intentional empty void.
export function VoidHatch({ region, px, py, scale }) {
  const x = px(region.x), y = py(region.y)
  const w = region.width * scale, h = region.height * scale
  const lines = []
  const step = 12
  for (let off = step; off < w + h; off += step) {
    let x1 = x + off, y1 = y
    let x2 = x, y2 = y + off
    if (x1 > x + w) { y1 = y + (x1 - (x + w)); x1 = x + w }
    if (y2 > y + h) { x2 = x + (y2 - (y + h)); y2 = y + h }
    lines.push(<Line key={off} points={[x1, y1, x2, y2]} stroke="rgba(139,148,158,0.16)" strokeWidth={1} listening={false} />)
  }
  return <>{lines}</>
}

export function GrillOverlay({ region, px, py, scale }) {
  const x = px(region.x), y = py(region.y)
  const pw = region.width * scale, ph = region.height * scale
  const mat = region.overlays?.[0]?.material
  if (!mat) return null

  if (mat === 'MS_SQUARE') {
    const lines = []
    const step = 8
    for (let i = step; i < pw; i += step)
      lines.push(<Line key={`v${i}`} points={[x + i, y, x + i, y + ph]} stroke="rgba(245,158,11,0.25)" strokeWidth={0.5} listening={false} />)
    for (let i = step; i < ph; i += step)
      lines.push(<Line key={`h${i}`} points={[x, y + i, x + pw, y + i]} stroke="rgba(245,158,11,0.25)" strokeWidth={0.5} listening={false} />)
    return <>{lines}</>
  }

  const bars = Math.max(1, Math.round((2 * region.height) - 2))
  const gap = ph / (bars + 1)
  const lines = []
  for (let i = 1; i <= bars; i++)
    lines.push(<Line key={i} points={[x + 2, y + gap * i, x + pw - 2, y + gap * i]} stroke="rgba(147,197,253,0.5)" strokeWidth={1.5} listening={false} />)
  return <>{lines}</>
}
