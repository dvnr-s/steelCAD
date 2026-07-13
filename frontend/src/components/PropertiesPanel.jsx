/**
 * Properties panel — shown on the right sidebar.
 * When a region is selected: shows type, pane spec, grill, hardware editors.
 * When nothing selected: shows tree-level design info.
 */
import { useState } from 'react'
import { Scissors, X, Plus } from 'lucide-react'
import toast from 'react-hot-toast'
import useEditorStore, { windowHingeCount } from '../store/editorStore'
import { fmtFt } from '../lib/format'

const REGION_TYPES = [
  { value: 'open',    label: 'Open', color: '#8b949e' },
  { value: 'fixed',   label: 'Fixed', color: '#22c55e' },
  { value: 'shutter', label: 'Shutter', color: '#f59e0b' },
  { value: 'door',    label: 'Door', color: '#ef4444' },
  { value: 'louver',  label: 'Louver', color: '#8b5cf6' },
]

function findRegion(region, id) {
  if (region.id === id) return region
  if (region.split) {
    for (const child of region.split.children) {
      const found = findRegion(child, id)
      if (found) return found
    }
  }
  return null
}

function SplitControls({ regionId }) {
  const [dir, setDir] = useState('vertical')
  const [pos, setPos] = useState(50)
  const splitRegion = useEditorStore((s) => s.splitRegion)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div className="flex gap-2">
        <button
          className={`btn btn-sm w-full ${dir === 'vertical' ? 'btn-primary' : 'btn-secondary'}`}
          onClick={() => setDir('vertical')}
        >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <rect x="1" y="1" width="12" height="12" rx="1" stroke="currentColor" strokeWidth="1.5" />
            <line x1="7" y1="1" x2="7" y2="13" stroke="currentColor" strokeWidth="1.5" />
          </svg>
          Vertical
        </button>
        <button
          className={`btn btn-sm w-full ${dir === 'horizontal' ? 'btn-primary' : 'btn-secondary'}`}
          onClick={() => setDir('horizontal')}
        >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <rect x="1" y="1" width="12" height="12" rx="1" stroke="currentColor" strokeWidth="1.5" />
            <line x1="1" y1="7" x2="13" y2="7" stroke="currentColor" strokeWidth="1.5" />
          </svg>
          Horizontal
        </button>
      </div>
      <div className="form-group">
        <label>Position: {pos}%</label>
        <input type="range" min="20" max="80" value={pos} onChange={(e) => setPos(+e.target.value)}
          style={{ padding: 0, height: 4, cursor: 'pointer' }} />
      </div>
      <button className="btn btn-primary btn-sm w-full"
        onClick={() => splitRegion(regionId, dir, pos / 100)}>
        <Scissors size={14} /> Split Region
      </button>
    </div>
  )
}

const MaterialSelect = ({ label, value, onChange }) => (
  <div className="form-group">
    <label>{label}</label>
    <select value={value || ''} onChange={(e) => onChange(e.target.value || null)}>
      <option value="">Select...</option>
      <option value="MS_PIPE">MS Pipe</option>
      <option value="GP_SHEET">GP Sheet</option>
    </select>
  </div>
)

function PaneSpecEditor({ region }) {
  const updateRegion = useEditorStore((s) => s.updateRegion)
  const ps = region.paneSpec || { shutterConfig: 'single', shutterMaterial: null, infillType: 'none', hasBeading: false, jaliMaterial: null, jaliBeading: false }
  const rt = region.regionType
  const isDouble = rt === 'shutter' && ps.shutterConfig === 'double'

  const update = (patch) =>
    updateRegion(region.id, { paneSpec: { ...ps, ...patch } })

  // Single ⇄ double shuttering (spec §10.4A). Double = a glass shutter on one
  // face of the frame + a jali shutter on the other; it forces glass infill and
  // auto-adds the jali-side (back) hinge set per HW-9. Back to single clears
  // the jali fields and strips back-side hardware.
  const setConfig = (config) => {
    if (config === (ps.shutterConfig || 'single')) return
    const hardware = region.hardware || []
    if (config === 'double') {
      const hasBackHinge = hardware.some((h) => h.hardwareType === 'hinge' && h.side === 'back')
      updateRegion(region.id, {
        paneSpec: { ...ps, shutterConfig: 'double', infillType: 'glass' },
        hardware: hasBackHinge ? hardware : [
          ...hardware,
          { id: crypto.randomUUID(), type: 'hardware', hardwareType: 'hinge', variant: 'SS_12G', quantity: windowHingeCount(region.height), autoComputed: true, side: 'back' },
        ],
      })
    } else {
      updateRegion(region.id, {
        paneSpec: { ...ps, shutterConfig: 'single', jaliMaterial: null, jaliBeading: false },
        hardware: hardware.filter((h) => h.side !== 'back'),
      })
    }
  }

  const canHaveInfill = rt !== 'door' && rt !== 'open' && rt !== 'louver'

  if (rt === 'open' || rt === 'louver') {
    return <p className="text-xs text-muted">No pane spec for {rt} regions</p>
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {rt === 'shutter' && (
        <div className="form-group">
          <label>Shuttering</label>
          <div className="flex gap-2">
            <button className={`btn btn-sm w-full ${!isDouble ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setConfig('single')}>Single</button>
            <button className={`btn btn-sm w-full ${isDouble ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setConfig('double')}>Double (glass + jali)</button>
          </div>
          {isDouble && (
            <p className="text-xs text-muted" style={{ marginTop: 6, lineHeight: 1.5 }}>
              Glass shutter on one side of the frame, jali shutter on the other — both panes fully priced, each hinged separately.
            </p>
          )}
        </div>
      )}

      {isDouble ? (
        <>
          <MaterialSelect label="Glass Shutter Material" value={ps.shutterMaterial}
            onChange={(v) => update({ shutterMaterial: v })} />
          <label className="flex items-center gap-2" style={{ cursor: 'pointer', fontSize: '0.875rem' }}>
            <input type="checkbox" checked={ps.hasBeading || false}
              onChange={(e) => update({ hasBeading: e.target.checked })} />
            Beading (glass side)
          </label>
          <MaterialSelect label="Jali Shutter Material" value={ps.jaliMaterial}
            onChange={(v) => update({ jaliMaterial: v })} />
          <label className="flex items-center gap-2" style={{ cursor: 'pointer', fontSize: '0.875rem' }}>
            <input type="checkbox" checked={ps.jaliBeading || false}
              onChange={(e) => update({ jaliBeading: e.target.checked })} />
            Beading (jali side)
          </label>
        </>
      ) : (
        <>
          {rt === 'shutter' && (
            <MaterialSelect label="Shutter Material" value={ps.shutterMaterial}
              onChange={(v) => update({ shutterMaterial: v })} />
          )}
          {canHaveInfill && (
            <div className="form-group">
              <label>Infill</label>
              <select value={ps.infillType || 'none'} onChange={(e) => update({ infillType: e.target.value })}>
                <option value="none">None</option>
                <option value="glass">Glass</option>
                <option value="jali">Jali</option>
              </select>
            </div>
          )}
          {canHaveInfill && ps.infillType !== 'none' && (
            <label className="flex items-center gap-2" style={{ cursor: 'pointer', fontSize: '0.875rem' }}>
              <input type="checkbox" checked={ps.hasBeading || false}
                onChange={(e) => update({ hasBeading: e.target.checked })} />
              Add Beading
            </label>
          )}
        </>
      )}
    </div>
  )
}

function GrillEditor({ region }) {
  const updateRegion = useEditorStore((s) => s.updateRegion)
  const overlays = region.overlays || []
  const grill = overlays.find((o) => o.overlayType === 'grill')

  const setGrill = (material) => {
    if (!material) {
      updateRegion(region.id, { overlays: [] })
    } else {
      updateRegion(region.id, {
        overlays: [{
          id: crypto.randomUUID(),
          type: 'overlay',
          overlayType: 'grill',
          material,
        }],
      })
    }
  }

  // MS grill only on leaves
  const showMS = region.isLeaf

  return (
    <div className="form-group">
      <label>Grill Type</label>
      <select value={grill?.material || ''} onChange={(e) => setGrill(e.target.value || null)}>
        <option value="">No Grill</option>
        {showMS && <option value="MS_SQUARE">MS Square</option>}
        <option value="SS_PIPE_ROUND">SS Pipe Round</option>
        <option value="SS_PIPE_SQUARE">SS Pipe Square</option>
      </select>
    </div>
  )
}

function HardwareEditor({ region }) {
  const updateRegion = useEditorStore((s) => s.updateRegion)
  const hardware = region.hardware || []
  const rt = region.regionType
  const isDoubleRebate = rt === 'door' && region.rebate === 'double'
  // A double shutter (§5.7) is hinged per shutter leaf: front = glass side, back = jali side.
  const isDoubleShutter = rt === 'shutter' && (region.paneSpec || {}).shutterConfig === 'double'
  const hasSides = isDoubleRebate || isDoubleShutter

  if (rt !== 'shutter' && rt !== 'door') {
    return <p className="text-xs text-muted">Hardware only on shutter/door regions</p>
  }

  const addHinge = (side = 'front') => {
    updateRegion(region.id, {
      hardware: [
        ...hardware,
        { id: crypto.randomUUID(), type: 'hardware', hardwareType: 'hinge', variant: 'SS_12G', quantity: 2, autoComputed: false, side },
      ],
    })
  }

  const addLock = (side = 'front') => {
    if (rt !== 'door') return
    updateRegion(region.id, {
      hardware: [
        ...hardware,
        { id: crypto.randomUUID(), type: 'hardware', hardwareType: 'lock', variant: 'standard', quantity: 1, autoComputed: false, side },
      ],
    })
  }

  const removeHw = (id) =>
    updateRegion(region.id, { hardware: hardware.filter((h) => h.id !== id) })

  const updateHw = (id, patch) =>
    updateRegion(region.id, { hardware: hardware.map((h) => h.id === id ? { ...h, ...patch } : h) })

  const HwRow = ({ hw }) => (
    <div key={hw.id} className="flex items-center gap-2" style={{
      background: 'var(--c-surface-2)',
      border: '1px solid var(--c-border)',
      borderRadius: 'var(--radius)',
      padding: '6px 8px',
    }}>
      <span className="text-xs text-muted" style={{ flex: 1 }}>{hw.hardwareType}</span>
      {hw.hardwareType === 'hinge' && (
        <select
          style={{ width: 100, fontSize: '0.75rem', padding: '2px 6px' }}
          value={hw.variant}
          onChange={(e) => updateHw(hw.id, { variant: e.target.value })}
        >
          <option value="SS_12G">SS 12G</option>
          <option value="SS_10G">SS 10G</option>
        </select>
      )}
      <input
        type="number" min="1" max="10"
        value={hw.quantity}
        onChange={(e) => updateHw(hw.id, { quantity: +e.target.value })}
        style={{ width: 44, fontSize: '0.75rem', padding: '2px 6px' }}
      />
      <button className="btn btn-ghost btn-icon" style={{ padding: 2 }}
        onClick={() => removeHw(hw.id)}>
        <X size={12} color="var(--c-error)" />
      </button>
    </div>
  )

  // Split hardware by side so a double-rebate door shows front / back groups.
  const front = hardware.filter((h) => (h.side || 'front') !== 'back')
  const back = hardware.filter((h) => h.side === 'back')

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {hasSides && (
        <div className="text-xs text-muted" style={{ fontWeight: 600 }}>
          {isDoubleShutter ? 'Glass shutter (front)' : 'Front side'}
        </div>
      )}
      {front.map((hw) => <HwRow key={hw.id} hw={hw} />)}
      <div className="flex gap-2">
        <button className="btn btn-secondary btn-sm" style={{ flex: 1 }} onClick={() => addHinge('front')}>
          <Plus size={12} /> Hinge
        </button>
        {rt === 'door' && (
          <button className="btn btn-secondary btn-sm" style={{ flex: 1 }} onClick={() => addLock('front')}>
            <Plus size={12} /> Lock
          </button>
        )}
      </div>

      {hasSides && (
        <>
          <div className="text-xs text-muted" style={{ fontWeight: 600, marginTop: 6 }}>
            {isDoubleShutter ? 'Jali shutter (back)' : 'Other side (back)'}
          </div>
          {back.map((hw) => <HwRow key={hw.id} hw={hw} />)}
          <div className="flex gap-2">
            <button className="btn btn-secondary btn-sm" style={{ flex: 1 }} onClick={() => addHinge('back')}>
              <Plus size={12} /> Hinge
            </button>
            {rt === 'door' && (
              <button className="btn btn-secondary btn-sm" style={{ flex: 1 }} onClick={() => addLock('back')}>
                <Plus size={12} /> Lock
              </button>
            )}
          </div>
        </>
      )}
    </div>
  )
}

// Door-only options: hand label + rebate (spec §4A.4 / §4A.5).
function DoorOptionsEditor({ region }) {
  const updateRegion = useEditorStore((s) => s.updateRegion)
  const hand = region.doorHand || null
  const rebate = region.rebate || 'single'

  const setHand = (h) => updateRegion(region.id, { doorHand: hand === h ? null : h })

  const setRebate = (r) => {
    // Dropping to single rebate strips any back-side hardware (V-16).
    if (r === 'single') {
      const hardware = (region.hardware || []).filter((h) => h.side !== 'back')
      updateRegion(region.id, { rebate: r, hardware })
    } else {
      updateRegion(region.id, { rebate: r })
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div className="form-group">
        <label>Hand</label>
        <div className="flex gap-2">
          <button className={`btn btn-sm w-full ${hand === 'left' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setHand('left')}>Left</button>
          <button className={`btn btn-sm w-full ${hand === 'right' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setHand('right')}>Right</button>
        </div>
      </div>
      <div className="form-group">
        <label>Rebate</label>
        <div className="flex gap-2">
          <button className={`btn btn-sm w-full ${rebate === 'single' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setRebate('single')}>Single</button>
          <button className={`btn btn-sm w-full ${rebate === 'double' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setRebate('double')}>Double</button>
        </div>
        {rebate === 'double' && (
          <p className="text-xs text-muted" style={{ marginTop: 6, lineHeight: 1.5 }}>
            Same frame price as single — double rebate just lets you add hinges/lock on the other side.
          </p>
        )}
      </div>
    </div>
  )
}

// Guided "add a window beside/above a door" (§4A.3). Carves a column off the
// door; partial-height windows leave an empty void.
function AddWindowEditor({ region }) {
  const addWindowToDoor = useEditorStore((s) => s.addWindowToDoor)
  const [side, setSide] = useState('right')
  const [width, setWidth] = useState(2)
  const [height, setHeight] = useState(4)
  const [vAlign, setVAlign] = useState('top')
  const [windowType, setWindowType] = useState('fixed')
  const isTop = side === 'top'

  const add = () => {
    const ok = addWindowToDoor(region.id, {
      side, width: Number(width), height: Number(height), vAlign, windowType,
    })
    if (!ok) toast.error('Window does not fit — enlarge the door or shrink the window')
  }

  const sideBtn = (val, label) => (
    <button className={`btn btn-sm w-full ${side === val ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setSide(val)}>{label}</button>
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div className="form-group">
        <label>Side</label>
        <div className="flex gap-2">{sideBtn('left', 'Left')}{sideBtn('right', 'Right')}{sideBtn('top', 'Top')}</div>
      </div>
      <div className="flex gap-3">
        {!isTop && (
          <div className="form-group" style={{ flex: 1 }}>
            <label>Width (ft)</label>
            <input type="number" min="0.5" step="0.5" value={width} onChange={(e) => setWidth(e.target.value)} />
          </div>
        )}
        <div className="form-group" style={{ flex: 1 }}>
          <label>Height (ft)</label>
          <input type="number" min="0.5" step="0.5" value={height} onChange={(e) => setHeight(e.target.value)} />
        </div>
      </div>
      {!isTop && (
        <div className="form-group">
          <label>Vertical align</label>
          <div className="flex gap-2">
            {['top', 'center', 'bottom'].map((v) => (
              <button key={v} className={`btn btn-sm w-full ${vAlign === v ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setVAlign(v)}>
                {v[0].toUpperCase() + v.slice(1)}
              </button>
            ))}
          </div>
        </div>
      )}
      <div className="form-group">
        <label>Window type</label>
        <div className="flex gap-2">
          <button className={`btn btn-sm w-full ${windowType === 'fixed' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setWindowType('fixed')}>Fixed</button>
          <button className={`btn btn-sm w-full ${windowType === 'shutter' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setWindowType('shutter')}>Shutter</button>
        </div>
      </div>
      <button className="btn btn-primary btn-sm w-full" onClick={add}>
        <Plus size={14} /> Add Window
      </button>
      <p className="text-xs text-muted" style={{ lineHeight: 1.5 }}>
        {isTop ? 'A full-width fanlight above the door.' : 'A window beside the door; a shorter window leaves an empty space.'}
      </p>
    </div>
  )
}

export default function PropertiesPanel() {
  const tree = useEditorStore((s) => s.tree)
  const selectedId = useEditorStore((s) => s.selectedId)
  const updateRegion = useEditorStore((s) => s.updateRegion)
  const collapseRegion = useEditorStore((s) => s.collapseRegion)
  const deselect = useEditorStore((s) => s.deselect)

  if (!tree) return null

  const selected = selectedId ? findRegion(tree.frame.rootRegion, selectedId) : null

  if (!selected) {
    return (
      <div>
        <div className="panel-section">
          <div className="panel-title">Design Info</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: '0.875rem' }}>
            <div className="flex justify-between">
              <span className="text-muted">Width</span>
              <span className="font-mono">{tree.outerWidth}ft</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted">Height</span>
              <span className="font-mono">{tree.outerHeight}ft</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted">Section</span>
              <span className="font-mono">{tree.sectionSize}" {tree.gauge}</span>
            </div>
          </div>
        </div>
        <div className="panel-section">
          <p className="text-xs text-muted" style={{ lineHeight: 1.6 }}>
            Click a region on the canvas to select it and edit its properties.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div>
      {/* Header */}
      <div className="panel-section">
        <div className="flex items-center justify-between" style={{ marginBottom: 8 }}>
          <div className="panel-title">Selected Region</div>
          <button className="btn btn-ghost btn-icon" style={{ padding: 2 }} onClick={deselect}>
            <X size={14} />
          </button>
        </div>
        <div style={{ fontSize: '0.8125rem', color: 'var(--c-text-muted)', fontFamily: 'var(--font-mono)' }}>
          {fmtFt(selected.height)}ft × {fmtFt(selected.width)}ft
        </div>
      </div>

      {/* Region Type (leaf only) */}
      {selected.isLeaf && (
        <div className="panel-section">
          <div className="panel-title">Type</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
            {REGION_TYPES.map((rt) => (
              <button
                key={rt.value}
                className={`btn btn-sm ${selected.regionType === rt.value ? 'btn-primary' : 'btn-secondary'}`}
                style={selected.regionType === rt.value ? {} : { borderColor: rt.color + '44', color: rt.color }}
                onClick={() => updateRegion(selected.id, {
                  regionType: rt.value,
                  paneSpec: null,
                  hardware: [],
                  doorHand: null,
                  rebate: 'single',
                  // A door has no pane or grill (§4A.2) — drop any overlay when switching to door.
                  ...(rt.value === 'door' ? { overlays: [] } : {}),
                })}
              >
                {rt.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Door options (hand + rebate) */}
      {selected.isLeaf && selected.regionType === 'door' && (
        <div className="panel-section">
          <div className="panel-title">Door Options</div>
          <DoorOptionsEditor region={selected} />
        </div>
      )}

      {/* Add a side / top window to a door (door products only, §4A.3) */}
      {selected.isLeaf && selected.regionType === 'door' && tree.productType === 'door' && (
        <div className="panel-section">
          <div className="panel-title">Add Window</div>
          <AddWindowEditor region={selected} />
        </div>
      )}

      {/* Pane Spec — shutter/fixed only. Door regions have no pane (§4A.2). */}
      {selected.isLeaf && (selected.regionType === 'shutter' || selected.regionType === 'fixed') && (
        <div className="panel-section">
          <div className="panel-title">Pane</div>
          <PaneSpecEditor region={selected} />
        </div>
      )}

      {/* Grill — not on door regions (§4A.2) */}
      {selected.regionType !== 'door' && (
        <div className="panel-section">
          <div className="panel-title">Grill</div>
          <GrillEditor region={selected} />
        </div>
      )}

      {/* Hardware */}
      {selected.isLeaf && (
        <div className="panel-section">
          <div className="panel-title">Hardware</div>
          <HardwareEditor region={selected} />
        </div>
      )}

      {/* Split */}
      {selected.isLeaf && (
        <div className="panel-section">
          <div className="panel-title">Split Region</div>
          <SplitControls regionId={selected.id} />
        </div>
      )}

      {/* Collapse (branch only) */}
      {!selected.isLeaf && (
        <div className="panel-section">
          <button
            className="btn btn-danger btn-sm w-full"
            onClick={() => collapseRegion(selected.id)}
          >
            <X size={14} /> Remove Split
          </button>
        </div>
      )}
    </div>
  )
}
