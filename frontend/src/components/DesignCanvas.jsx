/**
 * Canvas renderer — interactive design surface (Konva).
 *
 * Direct manipulation:
 *   - Drag a mullion (split line) to reposition it; sides resize live with
 *     dimension readouts and snap to 0.25 ft.
 *   - Double-click a mullion to delete it (merges the split back to one region).
 *   - With an "add mullion" tool active, hover shows a ghost line; click places it.
 *   - Drag the frame's right / bottom / corner handles to resize the whole unit.
 *
 * Geometry is derived by the store (relayout) — this component only reads
 * region x/y/width/height and translates feet ↔ pixels.
 */
import { useState } from 'react'
import { Stage, Layer, Rect, Line, Text, Group, Circle } from 'react-konva'
import useEditorStore, { snapOffset, MIN_SIDE } from '../store/editorStore'

const SCALE = 60          // pixels per foot
const BAR = 8             // mullion hit/visual thickness (px)
const HANDLE = 12         // frame resize handle size (px)

// Collect leaf regions + split descriptors (with parent bounds in feet).
function collect(region, acc) {
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

function leafAt(region, fx, fy) {
  if (region.isLeaf) {
    if (fx >= region.x && fx <= region.x + region.width &&
        fy >= region.y && fy <= region.y + region.height) return region
    return null
  }
  if (region.split) {
    for (const child of region.split.children) {
      const hit = leafAt(child, fx, fy)
      if (hit) return hit
    }
  }
  return null
}

function regionFill(region, selectedId) {
  if (region.id === selectedId) return 'rgba(59,130,246,0.18)'
  const rt = region.regionType
  if (rt === 'shutter') return 'rgba(245,158,11,0.08)'
  if (rt === 'door')    return 'rgba(239,68,68,0.08)'
  if (rt === 'fixed')   return 'rgba(34,197,94,0.06)'
  if (rt === 'louver')  return 'rgba(139,92,246,0.08)'
  return 'rgba(59,130,246,0.04)'
}

function regionStroke(region, selectedId) {
  if (region.id === selectedId) return '#3b82f6'
  const rt = region.regionType
  if (rt === 'shutter') return '#f59e0b'
  if (rt === 'door')    return '#ef4444'
  if (rt === 'fixed')   return '#22c55e'
  if (rt === 'louver')  return '#8b5cf6'
  return '#30363d'
}

function GrillOverlay({ region, px, py }) {
  const x = px(region.x), y = py(region.y)
  const pw = region.width * SCALE, ph = region.height * SCALE
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

export default function DesignCanvas({ width, height }) {
  const tree = useEditorStore((s) => s.tree)
  const selectedId = useEditorStore((s) => s.selectedId)
  const addMode = useEditorStore((s) => s.addMode)
  const select = useEditorStore((s) => s.select)
  const deselect = useEditorStore((s) => s.deselect)
  const splitRegion = useEditorStore((s) => s.splitRegion)
  const collapseRegion = useEditorStore((s) => s.collapseRegion)
  const setSplitPosition = useEditorStore((s) => s.setSplitPosition)
  const setFrameSize = useEditorStore((s) => s.setFrameSize)
  const beginInteraction = useEditorStore((s) => s.beginInteraction)
  const endInteraction = useEditorStore((s) => s.endInteraction)

  const [draggingId, setDraggingId] = useState(null)
  const [ghost, setGhost] = useState(null)

  if (!tree) return null

  const frame = tree.frame
  const fw = frame.width * SCALE
  const fh = frame.height * SCALE

  // Center the frame with margin for labels + handles.
  const offsetX = Math.max(48, (width - fw) / 2)
  const offsetY = Math.max(48, (height - fh) / 2)
  const px = (ft) => ft * SCALE + offsetX
  const py = (ft) => ft * SCALE + offsetY
  const toFeetX = (sx) => (sx - offsetX) / SCALE
  const toFeetY = (sy) => (sy - offsetY) / SCALE

  const { regions, splits } = collect(frame.rootRegion, { regions: [], splits: [] })

  // ── Add-mode ghost preview (hover) ───────────────────────
  const handleMouseMove = (e) => {
    if (!addMode) { if (ghost) setGhost(null); return }
    const pos = e.target.getStage().getPointerPosition()
    if (!pos) return
    const fx = toFeetX(pos.x), fy = toFeetY(pos.y)
    const leaf = leafAt(frame.rootRegion, fx, fy)
    if (!leaf) { setGhost(null); return }
    if (addMode === 'vertical') {
      const ratio = snapOffset(leaf.width, (fx - leaf.x) / leaf.width)
      const lineX = px(leaf.x + leaf.width * ratio)
      setGhost({ leafId: leaf.id, ratio, points: [lineX, py(leaf.y), lineX, py(leaf.y + leaf.height)] })
    } else {
      const ratio = snapOffset(leaf.height, (fy - leaf.y) / leaf.height)
      const lineY = py(leaf.y + leaf.height * ratio)
      setGhost({ leafId: leaf.id, ratio, points: [px(leaf.x), lineY, px(leaf.x + leaf.width), lineY] })
    }
  }

  const handleClick = (e) => {
    if (addMode && ghost) {
      splitRegion(ghost.leafId, addMode, ghost.ratio)
      setGhost(null)
      return
    }
    if (e.target === e.target.getStage()) deselect()
  }

  return (
    <Stage
      width={width}
      height={height}
      onClick={handleClick}
      onTap={handleClick}
      onMouseMove={handleMouseMove}
      style={{ cursor: addMode ? 'crosshair' : 'default' }}
    >
      <Layer>
        {/* Frame outline */}
        <Rect x={px(0)} y={py(0)} width={fw} height={fh} fill="transparent" stroke="#3b82f6" strokeWidth={3} listening={false} />

        {/* Frame dimension labels */}
        <Text x={px(frame.width / 2) - 20} y={py(0) - 22} text={`${frame.width}ft`} fontSize={11} fill="#8b949e" fontFamily="Inter, sans-serif" listening={false} />
        <Text x={px(0) - 30} y={py(frame.height / 2) - 8} text={`${frame.height}ft`} fontSize={11} fill="#8b949e" fontFamily="Inter, sans-serif" rotation={-90} listening={false} />

        {/* Regions */}
        {regions.map((region) => {
          const rx = px(region.x), ry = py(region.y)
          const rw = region.width * SCALE, rh = region.height * SCALE
          const isSelected = region.id === selectedId
          return (
            <Group key={region.id}>
              <Rect
                x={rx} y={ry} width={rw} height={rh}
                fill={regionFill(region, selectedId)}
                stroke={regionStroke(region, selectedId)}
                strokeWidth={isSelected ? 2 : 1}
                onClick={() => { if (!addMode) select(region.id) }}
                onTap={() => { if (!addMode) select(region.id) }}
              />
              {region.isLeaf && region.regionType && region.regionType !== 'open' && (
                <Text x={rx + 4} y={ry + 4} text={region.regionType.toUpperCase()} fontSize={9}
                  fill={regionStroke(region, selectedId)} fontFamily="JetBrains Mono, monospace" opacity={0.7} listening={false} />
              )}
              {rw > 40 && rh > 24 && (
                <Text x={rx + rw / 2 - 20} y={ry + rh / 2 - 7} text={`${region.width}×${region.height}`} fontSize={10}
                  fill="#484f58" fontFamily="JetBrains Mono, monospace" listening={false} />
              )}
              {region.overlays?.length > 0 && <GrillOverlay region={region} px={px} py={py} />}
            </Group>
          )
        })}

        {/* Draggable mullions */}
        {splits.map((s) => {
          const vertical = s.direction === 'vertical'
          const centerX = px(s.x + s.w * s.position)
          const centerY = py(s.y + s.h * s.position)
          const barX = vertical ? centerX - BAR / 2 : px(s.x)
          const barY = vertical ? py(s.y) : centerY - BAR / 2
          const barW = vertical ? BAR : s.w * SCALE
          const barH = vertical ? s.h * SCALE : BAR
          const dragging = draggingId === s.id

          return (
            <Group key={s.id}>
              <Rect
                x={barX} y={barY} width={barW} height={barH}
                fill={dragging ? '#3b82f6' : '#6b7280'}
                cornerRadius={2}
                draggable
                onMouseEnter={(e) => { e.target.getStage().container().style.cursor = vertical ? 'ew-resize' : 'ns-resize' }}
                onMouseLeave={(e) => { e.target.getStage().container().style.cursor = addMode ? 'crosshair' : 'default' }}
                dragBoundFunc={(pos) => {
                  if (vertical) {
                    const min = px(s.x + MIN_SIDE) - BAR / 2
                    const max = px(s.x + s.w - MIN_SIDE) - BAR / 2
                    return { x: Math.max(min, Math.min(max, pos.x)), y: py(s.y) }
                  }
                  const min = py(s.y + MIN_SIDE) - BAR / 2
                  const max = py(s.y + s.h - MIN_SIDE) - BAR / 2
                  return { x: px(s.x), y: Math.max(min, Math.min(max, pos.y)) }
                }}
                onDragStart={() => { beginInteraction(); setDraggingId(s.id) }}
                onDragMove={(e) => {
                  if (vertical) {
                    const ratio = (toFeetX(e.target.x() + BAR / 2) - s.x) / s.w
                    setSplitPosition(s.regionId, ratio)
                  } else {
                    const ratio = (toFeetY(e.target.y() + BAR / 2) - s.y) / s.h
                    setSplitPosition(s.regionId, ratio)
                  }
                }}
                onDragEnd={() => { endInteraction(); setDraggingId(null) }}
                onDblClick={() => collapseRegion(s.regionId)}
                onDblTap={() => collapseRegion(s.regionId)}
              />
              {/* Live side dimensions while dragging */}
              {dragging && vertical && (
                <>
                  <Text x={px(s.x) + (s.w * s.position * SCALE) / 2 - 16} y={py(s.y) + 6} text={`${(s.w * s.position).toFixed(2)}ft`} fontSize={11} fill="#3b82f6" fontFamily="JetBrains Mono, monospace" />
                  <Text x={centerX + (s.w * (1 - s.position) * SCALE) / 2 - 16} y={py(s.y) + 6} text={`${(s.w * (1 - s.position)).toFixed(2)}ft`} fontSize={11} fill="#3b82f6" fontFamily="JetBrains Mono, monospace" />
                </>
              )}
              {dragging && !vertical && (
                <>
                  <Text x={px(s.x) + 6} y={py(s.y) + (s.h * s.position * SCALE) / 2 - 6} text={`${(s.h * s.position).toFixed(2)}ft`} fontSize={11} fill="#3b82f6" fontFamily="JetBrains Mono, monospace" />
                  <Text x={px(s.x) + 6} y={centerY + (s.h * (1 - s.position) * SCALE) / 2 - 6} text={`${(s.h * (1 - s.position)).toFixed(2)}ft`} fontSize={11} fill="#3b82f6" fontFamily="JetBrains Mono, monospace" />
                </>
              )}
            </Group>
          )
        })}

        {/* Ghost preview for add-mode */}
        {ghost && <Line points={ghost.points} stroke="#3b82f6" strokeWidth={2} dash={[6, 4]} listening={false} />}

        {/* Frame resize handles */}
        <FrameHandle
          x={px(frame.width) - HANDLE / 2} y={py(frame.height / 2) - HANDLE / 2} size={HANDLE} cursor="ew-resize"
          bound={(pos) => ({ x: Math.max(px(MIN_SIDE), pos.x), y: py(frame.height / 2) - HANDLE / 2 })}
          onStart={beginInteraction}
          onMove={(e) => setFrameSize(toFeetX(e.target.x() + HANDLE / 2), frame.height)}
          onEnd={endInteraction}
        />
        <FrameHandle
          x={px(frame.width / 2) - HANDLE / 2} y={py(frame.height) - HANDLE / 2} size={HANDLE} cursor="ns-resize"
          bound={(pos) => ({ x: px(frame.width / 2) - HANDLE / 2, y: Math.max(py(MIN_SIDE), pos.y) })}
          onStart={beginInteraction}
          onMove={(e) => setFrameSize(frame.width, toFeetY(e.target.y() + HANDLE / 2))}
          onEnd={endInteraction}
        />
        <FrameHandle
          x={px(frame.width) - HANDLE / 2} y={py(frame.height) - HANDLE / 2} size={HANDLE} cursor="nwse-resize" corner
          bound={(pos) => ({ x: Math.max(px(MIN_SIDE), pos.x), y: Math.max(py(MIN_SIDE), pos.y) })}
          onStart={beginInteraction}
          onMove={(e) => setFrameSize(toFeetX(e.target.x()), toFeetY(e.target.y()))}
          onEnd={endInteraction}
        />
      </Layer>
    </Stage>
  )
}

function FrameHandle({ x, y, size, cursor, corner, bound, onStart, onMove, onEnd }) {
  const common = {
    draggable: true,
    dragBoundFunc: bound,
    onDragStart: onStart,
    onDragMove: onMove,
    onDragEnd: onEnd,
    onMouseEnter: (e) => { e.target.getStage().container().style.cursor = cursor },
    onMouseLeave: (e) => { e.target.getStage().container().style.cursor = 'default' },
  }
  return corner
    ? <Circle x={x + size / 2} y={y + size / 2} radius={size / 2} fill="#3b82f6" {...common} />
    : <Rect x={x} y={y} width={size} height={size} cornerRadius={2} fill="#3b82f6" {...common} />
}
