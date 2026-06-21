/**
 * Canvas renderer — draws the design tree on a Konva stage.
 * Each region is drawn as a rectangle. Selected region gets a highlight border.
 * Split lines are drawn in a muted color. Dimension labels shown on hover.
 */
import { Stage, Layer, Rect, Line, Text, Group } from 'react-konva'
import useEditorStore from '../store/editorStore'

const SCALE = 60 // pixels per foot

function collectRegions(region, regions = [], splits = []) {
  if (region.isLeaf) {
    regions.push(region)
  } else {
    // Draw the split line
    if (region.split) {
      const { direction, position } = region.split
      const { x, y, width: w, height: h } = region
      if (direction === 'vertical') {
        splits.push({
          id: region.split.id,
          points: [x + w * position, y, x + w * position, y + h],
        })
      } else {
        splits.push({
          id: region.split.id,
          points: [x, y + h * position, x + w, y + h * position],
        })
      }
      for (const child of region.split.children) {
        collectRegions(child, regions, splits)
      }
    }
    // Branch region with SS grill overlay
    if (region.overlays?.length) {
      regions.push({ ...region, _branchWithGrill: true })
    }
  }
  return { regions, splits }
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

function GrillOverlay({ region }) {
  const { x, y, width: w, height: h } = region
  const px = x * SCALE
  const py = y * SCALE
  const pw = w * SCALE
  const ph = h * SCALE
  const mat = region.overlays?.[0]?.material
  if (!mat) return null

  if (mat === 'MS_SQUARE') {
    // Crosshatch pattern
    const lines = []
    const step = 8
    for (let i = step; i < pw; i += step)
      lines.push(<Line key={`v${i}`} points={[px + i, py, px + i, py + ph]}
        stroke="rgba(245,158,11,0.25)" strokeWidth={0.5} />)
    for (let i = step; i < ph; i += step)
      lines.push(<Line key={`h${i}`} points={[px, py + i, px + pw, py + i]}
        stroke="rgba(245,158,11,0.25)" strokeWidth={0.5} />)
    return <>{lines}</>
  }

  // SS — horizontal bars
  const bars = Math.max(1, Math.round((2 * h) - 2))
  const gap = ph / (bars + 1)
  const lines = []
  for (let i = 1; i <= bars; i++) {
    lines.push(
      <Line key={i}
        points={[px + 2, py + gap * i, px + pw - 2, py + gap * i]}
        stroke="rgba(147,197,253,0.5)" strokeWidth={1.5} />
    )
  }
  return <>{lines}</>
}

export default function DesignCanvas({ width, height }) {
  const tree = useEditorStore((s) => s.tree)
  const selectedId = useEditorStore((s) => s.selectedId)
  const select = useEditorStore((s) => s.select)
  const deselect = useEditorStore((s) => s.deselect)

  if (!tree) return null

  const frame = tree.frame
  const fw = frame.width * SCALE
  const fh = frame.height * SCALE

  // Center the frame in the canvas
  const offsetX = Math.max(20, (width - fw) / 2)
  const offsetY = Math.max(20, (height - fh) / 2)

  const { regions, splits } = collectRegions(frame.rootRegion)

  const handleStageClick = (e) => {
    if (e.target === e.target.getStage()) deselect()
  }

  return (
    <Stage
      width={width}
      height={height}
      onClick={handleStageClick}
    >
      <Layer offsetX={-offsetX} offsetY={-offsetY}>
        {/* Frame */}
        <Rect
          x={0} y={0} width={fw} height={fh}
          fill="transparent"
          stroke="#3b82f6"
          strokeWidth={3}
        />

        {/* Dimension labels */}
        <Text
          x={fw / 2 - 20} y={-18}
          text={`${frame.width}ft`}
          fontSize={11} fill="#8b949e" fontFamily="Inter, sans-serif"
        />
        <Text
          x={-28} y={fh / 2 - 8}
          text={`${frame.height}ft`}
          fontSize={11} fill="#8b949e" fontFamily="Inter, sans-serif"
          rotation={-90}
        />

        {/* Split lines */}
        {splits.map((s) => (
          <Line key={s.id}
            points={s.points.map((v, i) => i % 2 === 0 ? v * SCALE : v * SCALE)}
            stroke="#484f58"
            strokeWidth={1.5}
            dash={[4, 4]}
          />
        ))}

        {/* Regions */}
        {regions.map((region) => {
          const rx = region.x * SCALE
          const ry = region.y * SCALE
          const rw = region.width * SCALE
          const rh = region.height * SCALE
          const isSelected = region.id === selectedId

          return (
            <Group key={region.id}>
              <Rect
                x={rx} y={ry} width={rw} height={rh}
                fill={regionFill(region, selectedId)}
                stroke={regionStroke(region, selectedId)}
                strokeWidth={isSelected ? 2 : 1}
                onClick={() => select(region.id)}
                onTap={() => select(region.id)}
                style={{ cursor: 'pointer' }}
              />
              {/* Region type label */}
              {region.isLeaf && region.regionType && region.regionType !== 'open' && (
                <Text
                  x={rx + 4} y={ry + 4}
                  text={region.regionType.toUpperCase()}
                  fontSize={9}
                  fill={regionStroke(region, selectedId)}
                  fontFamily="JetBrains Mono, monospace"
                  opacity={0.7}
                />
              )}
              {/* Dimension label */}
              {rw > 40 && rh > 24 && (
                <Text
                  x={rx + rw / 2 - 20}
                  y={ry + rh / 2 - 7}
                  text={`${region.width}×${region.height}`}
                  fontSize={10}
                  fill="#484f58"
                  fontFamily="JetBrains Mono, monospace"
                />
              )}
              {/* Grill overlay */}
              {region.overlays?.length > 0 && <GrillOverlay region={region} />}
            </Group>
          )
        })}
      </Layer>
    </Stage>
  )
}
