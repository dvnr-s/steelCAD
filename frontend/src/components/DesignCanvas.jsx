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
import { useState, useRef, useEffect } from 'react'
import { Stage, Layer, Rect, Line, Text, Group, Circle } from 'react-konva'
import { Minus, Plus, Maximize2 } from 'lucide-react'
import useEditorStore, { snapOffset, MIN_SIDE } from '../store/editorStore'
import { dimLabel } from '../lib/format'
import {
  ACTUAL_SCALE, FIT_PAD, fitScale, collect, regionFill, regionStroke, regionTag,
  DoorSwing, ConcreteBase, VoidHatch, GrillOverlay,
} from '../lib/canvasDraw'

const MIN_PPF = 6         // zoom-out limit (px/ft)
const MAX_PPF = 240       // zoom-in limit (px/ft)
const BAR = 8             // mullion hit/visual thickness (px)
const HANDLE = 12         // frame resize handle size (px)

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
  // View transform: screen = ft * scale + t. Null until first layout.
  const [view, setView] = useState(null)
  const [isPanning, setIsPanning] = useState(false)
  const panRef = useRef(null)        // active pan gesture state
  const initedRef = useRef(null)     // design id the view was initialized for

  // Initialize the view fit-to-viewport (up to the zoom-in cap): the frame
  // fills the available canvas, centered, once per design — and only once a
  // real measurement arrives (width/height are 0 until the ResizeObserver fires).
  useEffect(() => {
    if (!tree || width < 2 || height < 2) return
    if (initedRef.current === tree.id) return
    initedRef.current = tree.id
    const s = fitScale(tree.frame.width, tree.frame.height, width, height)
    const fw = tree.frame.width * s, fh = tree.frame.height * s
    setView({ scale: s, tx: (width - fw) / 2, ty: (height - fh) / 2 })
    // Keyed on the design id, not `tree`, so edits don't reset the user's zoom/pan.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tree?.id, width, height])

  if (!tree) return null

  const frame = tree.frame
  // First-paint fallback (before the init effect runs) matches the fit-to-view default.
  const fallbackScale = fitScale(frame.width, frame.height, width, height)
  const scale = view?.scale ?? fallbackScale
  const tx = view?.tx ?? (width - frame.width * fallbackScale) / 2
  const ty = view?.ty ?? (height - frame.height * fallbackScale) / 2
  const fw = frame.width * scale
  const fh = frame.height * scale
  const px = (ft) => ft * scale + tx
  const py = (ft) => ft * scale + ty
  const toFeetX = (sx) => (sx - tx) / scale
  const toFeetY = (sy) => (sy - ty) / scale

  const { regions, splits } = collect(frame.rootRegion, { regions: [], splits: [] })

  // ── Zoom / pan ───────────────────────────────────────────
  const clampScale = (s) => Math.max(MIN_PPF, Math.min(MAX_PPF, s))

  // Zoom toward a screen anchor so the world point under it stays put.
  const zoomToPoint = (nextScale, ax, ay) => {
    const ns = clampScale(nextScale)
    const wx = (ax - tx) / scale, wy = (ay - ty) / scale
    setView({ scale: ns, tx: ax - wx * ns, ty: ay - wy * ns })
  }
  const zoomByFactor = (f) => zoomToPoint(scale * f, width / 2, height / 2)
  const resetActual = () => {
    const fw = frame.width * ACTUAL_SCALE, fh = frame.height * ACTUAL_SCALE
    setView({ scale: ACTUAL_SCALE, tx: Math.max(FIT_PAD, (width - fw) / 2), ty: Math.max(FIT_PAD, (height - fh) / 2) })
  }
  const fitToView = () => {
    const fs = fitScale(frame.width, frame.height, width, height)
    setView({ scale: fs, tx: (width - frame.width * fs) / 2, ty: (height - frame.height * fs) / 2 })
  }

  const handleWheel = (e) => {
    e.evt.preventDefault()
    const pos = e.target.getStage().getPointerPosition()
    if (!pos) return
    zoomToPoint(scale * (e.evt.deltaY < 0 ? 1.1 : 1 / 1.1), pos.x, pos.y)
  }

  // ── Add-mode ghost preview (hover) + panning ─────────────
  const handleMouseMove = (e) => {
    if (panRef.current) {
      const pos = e.target.getStage().getPointerPosition()
      if (!pos) return
      const dx = pos.x - panRef.current.x, dy = pos.y - panRef.current.y
      if (!panRef.current.moved && (Math.abs(dx) > 3 || Math.abs(dy) > 3)) {
        panRef.current.moved = true
        setIsPanning(true)
      }
      if (panRef.current.moved) setView({ scale, tx: panRef.current.tx + dx, ty: panRef.current.ty + dy })
      return
    }
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

  // Start a pan only when pressing empty canvas (not a mullion/handle).
  const handleMouseDown = (e) => {
    if (addMode) return
    const stage = e.target.getStage()
    if (e.target !== stage) return
    const pos = stage.getPointerPosition()
    panRef.current = { x: pos.x, y: pos.y, tx, ty, moved: false }
  }

  const handleMouseUp = (e) => {
    const pan = panRef.current
    panRef.current = null
    if (isPanning) setIsPanning(false)
    // A press-release on empty space with no drag clears the selection.
    if (!addMode && pan && !pan.moved && e.target === e.target.getStage()) deselect()
  }

  // Mouse click handles add-mode placement only (deselect lives in mouseup so a
  // pan-drag doesn't clear the selection).
  const handleClick = () => {
    if (addMode && ghost) {
      splitRegion(ghost.leafId, addMode, ghost.ratio)
      setGhost(null)
    }
  }

  // Touch: no panning, so tap places (add-mode) or deselects.
  const handleTap = (e) => {
    if (addMode && ghost) {
      splitRegion(ghost.leafId, addMode, ghost.ratio)
      setGhost(null)
      return
    }
    if (e.target === e.target.getStage()) deselect()
  }

  const zoomPct = Math.round((scale / ACTUAL_SCALE) * 100)

  return (
    <>
    <Stage
      width={width}
      height={height}
      onClick={handleClick}
      onTap={handleTap}
      onWheel={handleWheel}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
      style={{ cursor: addMode ? 'crosshair' : isPanning ? 'grabbing' : 'grab' }}
    >
      <Layer>
        {/* Frame outline */}
        <Rect x={px(0)} y={py(0)} width={fw} height={fh} fill="transparent" stroke="#3b82f6" strokeWidth={3} listening={false} />

        {/* Door product: base sits in the concrete (3-sided frame) */}
        {tree.productType === 'door' && <ConcreteBase frame={frame} px={px} py={py} />}

        {/* Frame dimension labels */}
        <Text x={px(frame.width / 2) - 20} y={py(0) - 22} text={`${frame.width}ft`} fontSize={11} fill="#8b949e" fontFamily="Inter, sans-serif" listening={false} />
        <Text x={px(0) - 30} y={py(frame.height / 2) - 8} text={`${frame.height}ft`} fontSize={11} fill="#8b949e" fontFamily="Inter, sans-serif" rotation={-90} listening={false} />

        {/* Regions */}
        {regions.map((region) => {
          const rx = px(region.x), ry = py(region.y)
          const rw = region.width * scale, rh = region.height * scale
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
              {region.isLeaf && regionTag(region) && (
                <Text x={rx + 4} y={ry + 4} text={regionTag(region)} fontSize={9}
                  fill={regionStroke(region, selectedId)} fontFamily="JetBrains Mono, monospace" opacity={0.7} listening={false} />
              )}
              {rw > 40 && rh > 24 && (
                <Text x={rx + rw / 2 - 20} y={ry + rh / 2 - 7} text={dimLabel(region)} fontSize={10}
                  fill="#484f58" fontFamily="JetBrains Mono, monospace" listening={false} />
              )}
              {region.overlays?.length > 0 && <GrillOverlay region={region} px={px} py={py} scale={scale} />}
              {region.isLeaf && region.regionType === 'open' && (
                <VoidHatch region={region} px={px} py={py} scale={scale} />
              )}
              {region.isLeaf && region.regionType === 'door' && (
                <>
                  <DoorSwing region={region} px={px} py={py} scale={scale} />
                  {(region.doorHand || region.rebate === 'double') && rw > 40 && (
                    <Text x={rx + rw - 34} y={ry + 4} text={`${region.doorHand ? region.doorHand[0].toUpperCase() : ''}${region.rebate === 'double' ? ' 2R' : ''}`.trim()}
                      fontSize={9} fill="#ef4444" fontFamily="JetBrains Mono, monospace" opacity={0.8} listening={false} />
                  )}
                </>
              )}
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
          const barW = vertical ? BAR : s.w * scale
          const barH = vertical ? s.h * scale : BAR
          const dragging = draggingId === s.id

          return (
            <Group key={s.id}>
              <Rect
                x={barX} y={barY} width={barW} height={barH}
                fill={dragging ? '#3b82f6' : '#6b7280'}
                cornerRadius={2}
                draggable
                onMouseEnter={(e) => { e.target.getStage().container().style.cursor = vertical ? 'ew-resize' : 'ns-resize' }}
                onMouseLeave={(e) => { e.target.getStage().container().style.cursor = addMode ? 'crosshair' : 'grab' }}
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
                  <Text x={px(s.x) + (s.w * s.position * scale) / 2 - 16} y={py(s.y) + 6} text={`${(s.w * s.position).toFixed(2)}ft`} fontSize={11} fill="#3b82f6" fontFamily="JetBrains Mono, monospace" />
                  <Text x={centerX + (s.w * (1 - s.position) * scale) / 2 - 16} y={py(s.y) + 6} text={`${(s.w * (1 - s.position)).toFixed(2)}ft`} fontSize={11} fill="#3b82f6" fontFamily="JetBrains Mono, monospace" />
                </>
              )}
              {dragging && !vertical && (
                <>
                  <Text x={px(s.x) + 6} y={py(s.y) + (s.h * s.position * scale) / 2 - 6} text={`${(s.h * s.position).toFixed(2)}ft`} fontSize={11} fill="#3b82f6" fontFamily="JetBrains Mono, monospace" />
                  <Text x={px(s.x) + 6} y={centerY + (s.h * (1 - s.position) * scale) / 2 - 6} text={`${(s.h * (1 - s.position)).toFixed(2)}ft`} fontSize={11} fill="#3b82f6" fontFamily="JetBrains Mono, monospace" />
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

    {/* Zoom controls — true size is 100% (60px/ft); wheel zooms, drag pans. */}
    <div style={{
      position: 'absolute', right: 16, bottom: 16, zIndex: 10,
      display: 'flex', gap: 2, alignItems: 'center', padding: 4,
      background: 'var(--c-surface-2)', border: '1px solid var(--c-border)',
      borderRadius: 'var(--radius)', boxShadow: '0 2px 8px rgba(0,0,0,0.2)',
    }}>
      <button className="btn btn-ghost btn-sm btn-icon" title="Zoom out" onClick={() => zoomByFactor(1 / 1.2)}><Minus size={15} /></button>
      <button className="btn btn-ghost btn-sm" style={{ minWidth: 50 }} title="Reset to actual size (100%)" onClick={resetActual}>{zoomPct}%</button>
      <button className="btn btn-ghost btn-sm btn-icon" title="Zoom in" onClick={() => zoomByFactor(1.2)}><Plus size={15} /></button>
      <button className="btn btn-ghost btn-sm" title="Fit to view" onClick={fitToView}><Maximize2 size={14} /> Fit</button>
    </div>
    </>
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
    onMouseLeave: (e) => { e.target.getStage().container().style.cursor = 'grab' },
  }
  return corner
    ? <Circle x={x + size / 2} y={y + size / 2} radius={size / 2} fill="#3b82f6" {...common} />
    : <Rect x={x} y={y} width={size} height={size} cornerRadius={2} fill="#3b82f6" {...common} />
}
