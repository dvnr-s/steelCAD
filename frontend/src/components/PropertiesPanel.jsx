/**
 * Properties panel — shown on the right sidebar.
 * When a region is selected: shows type, pane spec, grill, hardware editors.
 * When nothing selected: shows tree-level design info.
 */
import { useState } from 'react'
import { Scissors, X, Plus, Minus, Copy, ClipboardPaste, Layers, RotateCcw } from 'lucide-react'
import toast from 'react-hot-toast'
import useEditorStore, { doorHingeCount, windowHingeCount } from '../store/editorStore'
import { fmtFtIn } from '../lib/format'
import { grillBarAdjust, ssGrillAutoBars, ssGrillBarCount, ssGrillMaxBars } from '../lib/grill'
import DimensionInput from './DimensionInput'

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

const MaterialSelect = ({ label, value, onChange, allowHingesOnly = false }) => (
  <div className="form-group">
    <label>{label}</label>
    <select value={value || ''} onChange={(e) => onChange(e.target.value || null)}>
      <option value="">Select...</option>
      <option value="MS_PIPE">MS Pipe</option>
      <option value="GP_SHEET">GP Sheet</option>
      {/* §5.8: customer-supplied shutter — hinges only, no pane/infill/beading */}
      {allowHingesOnly && <option value="HINGES_ONLY">No Shutter, only Hinges</option>}
    </select>
  </div>
)

function PaneSpecEditor({ region }) {
  const updateRegion = useEditorStore((s) => s.updateRegion)
  const ps = region.paneSpec || { shutterConfig: 'single', shutterMaterial: null, infillType: 'none', hasBeading: false, jaliMaterial: null, jaliBeading: false }
  const rt = region.regionType
  const isDouble = rt === 'shutter' && ps.shutterConfig === 'double'
  // §5.8: HINGES_ONLY = customer-supplied shutter; we charge hinges only.
  const isHingesOnly = rt === 'shutter' && ps.shutterMaterial === 'HINGES_ONLY'

  const update = (patch) =>
    updateRegion(region.id, { paneSpec: { ...ps, ...patch } })

  // Selecting the shutter material. HINGES_ONLY (§5.8) is customer-supplied:
  // clear infill/beading/jali so only hinges remain (V-21). Leaving HINGES_ONLY
  // while double restores the fabricated-double invariant (glass side implied).
  const setShutterMaterial = (v) => {
    if (v === 'HINGES_ONLY') {
      update({ shutterMaterial: v, infillType: 'none', hasBeading: false, jaliMaterial: null, jaliBeading: false })
    } else if (ps.shutterConfig === 'double') {
      update({ shutterMaterial: v, infillType: 'glass' })
    } else {
      update({ shutterMaterial: v })
    }
  }

  // Single ⇄ double shuttering (spec §10.4A). Fabricated double = a glass shutter
  // on one face + a jali shutter on the other (forces glass infill). A HINGES_ONLY
  // double (§5.8) is customer-supplied on both faces (no infill). Either way the
  // jali-side (back) hinge set is auto-added per HW-9; back to single clears the
  // jali fields and strips back-side hardware.
  const setConfig = (config) => {
    if (config === (ps.shutterConfig || 'single')) return
    const hardware = region.hardware || []
    if (config === 'double') {
      const hasBackHinge = hardware.some((h) => h.hardwareType === 'hinge' && h.side === 'back')
      const nextPane = isHingesOnly
        ? { ...ps, shutterConfig: 'double' }                    // customer-supplied: no glass infill
        : { ...ps, shutterConfig: 'double', infillType: 'glass' }
      updateRegion(region.id, {
        paneSpec: nextPane,
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
            <button className={`btn btn-sm w-full ${isDouble ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setConfig('double')}>{isHingesOnly ? 'Double' : 'Double (glass + jali)'}</button>
          </div>
          {isDouble && !isHingesOnly && (
            <p className="text-xs text-muted" style={{ marginTop: 6, lineHeight: 1.5 }}>
              Glass shutter on one side of the frame, jali shutter on the other — both panes fully priced, each hinged separately.
            </p>
          )}
          {isDouble && isHingesOnly && (
            <p className="text-xs text-muted" style={{ marginTop: 6, lineHeight: 1.5 }}>
              Customer supplies a shutter on each face; we hinge both sides.
            </p>
          )}
        </div>
      )}

      {rt === 'shutter' && (
        <MaterialSelect label={isDouble && !isHingesOnly ? 'Glass Shutter Material' : 'Shutter Material'}
          value={ps.shutterMaterial} allowHingesOnly onChange={setShutterMaterial} />
      )}

      {isHingesOnly ? (
        <p className="text-xs text-muted" style={{ lineHeight: 1.5 }}>
          Customer supplies the shutter{isDouble ? 's (both faces)' : ''}; we provide hinges only. No pane, infill, or beading is charged.
        </p>
      ) : isDouble ? (
        <>
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
  const isSS = grill && grill.material !== 'MS_SQUARE'
  const barAdjust = grillBarAdjust(grill)

  const setGrill = (material) => {
    if (!material) {
      updateRegion(region.id, { overlays: [] })
      return
    }
    // §6.2A: the manual bar delta survives switching between SS materials.
    const keepAdjust = isSS && material !== 'MS_SQUARE' ? barAdjust : 0
    updateRegion(region.id, {
      overlays: [{
        id: crypto.randomUUID(),
        type: 'overlay',
        overlayType: 'grill',
        material,
        config: {
          is_continuity: !region.isLeaf,
          ...(keepAdjust ? { barAdjust: keepAdjust } : {}),
        },
      }],
    })
  }

  const setAdjust = (next) => {
    const bars = ssGrillBarCount(region.height, next)
    if (next !== 0 && (bars < 1 || bars > ssGrillMaxBars(region.height))) return // V-20 — clamp at the stepper
    updateRegion(region.id, {
      overlays: [{ ...grill, config: { ...(grill.config || {}), barAdjust: next } }],
    })
  }

  // Adding a grill is offered on fixed/shutter leaves and on branches (SS
  // continuity) — §10.3 step 5. An existing grill elsewhere (legacy data)
  // stays visible so it can still be removed.
  const rt = region.regionType
  const canAdd = !region.isLeaf || rt === 'fixed' || rt === 'shutter'
  if (!grill && !canAdd) {
    return <p className="text-xs text-muted">Grill applies to fixed/shutter regions only</p>
  }

  // MS grill only on leaves
  const showMS = region.isLeaf

  const bars = ssGrillBarCount(region.height, barAdjust)
  const autoBars = ssGrillAutoBars(region.height)
  const maxBars = ssGrillMaxBars(region.height)
  const rft = Math.round(bars * region.width * 100) / 100

  return (
    <div className="form-group">
      <label>Grill Type</label>
      <select value={grill?.material || ''} onChange={(e) => setGrill(e.target.value || null)}>
        <option value="">No Grill</option>
        {showMS && <option value="MS_SQUARE">MS Square</option>}
        <option value="SS_PIPE_ROUND">SS Pipe Round</option>
        <option value="SS_PIPE_SQUARE">SS Pipe Square</option>
      </select>

      {/* Billed bar count — always the same bars the canvas draws (§6.2/§6.2A) */}
      {isSS && (
        <div style={{ marginTop: 8 }}>
          <label>Bars</label>
          <div className="flex gap-2" style={{ alignItems: 'center' }}>
            <button className="btn btn-sm btn-secondary btn-icon" title="One bar fewer"
              onClick={() => setAdjust(barAdjust - 1)} disabled={bars <= 1}>
              <Minus size={13} />
            </button>
            <span className="text-sm" style={{ minWidth: 90, textAlign: 'center' }}>
              {bars} bars{barAdjust !== 0 && ` (auto ${autoBars}, ${barAdjust > 0 ? '+' : ''}${barAdjust})`}
            </span>
            <button className="btn btn-sm btn-secondary btn-icon" title="One bar more"
              onClick={() => setAdjust(barAdjust + 1)} disabled={bars >= maxBars}>
              <Plus size={13} />
            </button>
            {barAdjust !== 0 && (
              <button className="btn btn-sm btn-ghost btn-icon" title="Reset to auto count"
                onClick={() => setAdjust(0)}>
                <RotateCcw size={13} />
              </button>
            )}
          </div>
          <p className="text-xs text-muted" style={{ marginTop: 4 }}>
            {bars} × {fmtFtIn(region.width)} = {rft} RFT billed
          </p>
        </div>
      )}
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
            <label>Width</label>
            <DimensionInput value={width} onCommit={(v) => setWidth(v)} title={'Decimal feet or ft-in (e.g. 2\'6")'} />
          </div>
        )}
        <div className="form-group" style={{ flex: 1 }}>
          <label>Height</label>
          <DimensionInput value={height} onCommit={(v) => setHeight(v)} title={'Decimal feet or ft-in (e.g. 4\'6")'} />
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

// Exact mullion/transom position editor for a selected branch (split) region.
// The offset is measured from the parent's left (vertical) or top (horizontal)
// edge; typing a value snaps to the 3" grid like a drag would.
function SplitPositionEditor({ region }) {
  const setSplitPosition = useEditorStore((s) => s.setSplitPosition)
  const vertical = region.split.direction === 'vertical'
  const axis = vertical ? region.width : region.height
  const offset = axis * region.split.position

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div className="form-group">
        <label>{vertical ? 'Offset from left edge' : 'Offset from top edge'}</label>
        <DimensionInput
          value={offset}
          onCommit={(v) => setSplitPosition(region.id, v / axis, { history: true })}
          title={'Decimal feet or ft-in (e.g. 2\'6") — snaps to 3"'}
        />
      </div>
      <div className="flex justify-between" style={{ fontSize: '0.8125rem', color: 'var(--c-text-muted)' }}>
        <span>{vertical ? 'Left panel' : 'Top panel'}</span>
        <span className="font-mono">{fmtFtIn(offset)}</span>
      </div>
      <div className="flex justify-between" style={{ fontSize: '0.8125rem', color: 'var(--c-text-muted)' }}>
        <span>{vertical ? 'Right panel' : 'Bottom panel'}</span>
        <span className="font-mono">{fmtFtIn(axis - offset)}</span>
      </div>
    </div>
  )
}

// Copy the selected leaf's spec, paste onto it, or sweep the clipboard across
// every leaf of the same region type (one undo step).
function ClipboardSection({ region }) {
  const clipboard = useEditorStore((s) => s.clipboard)
  const copyRegion = useEditorStore((s) => s.copyRegion)
  const pasteOnto = useEditorStore((s) => s.pasteOnto)
  const pasteOntoAllSimilar = useEditorStore((s) => s.pasteOntoAllSimilar)

  const applyAll = () => {
    const n = pasteOntoAllSimilar()
    if (n > 0) toast.success(`Applied to ${n} ${clipboard.regionType} region${n > 1 ? 's' : ''}`)
    else toast.error(`No ${clipboard.regionType} regions to apply to`)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <button className="btn btn-secondary btn-sm w-full"
        onClick={() => { if (copyRegion(region.id)) toast.success('Region copied') }}>
        <Copy size={13} /> Copy region spec (Ctrl+C)
      </button>
      {clipboard && (
        <>
          <button className="btn btn-secondary btn-sm w-full" onClick={() => pasteOnto(region.id)}>
            <ClipboardPaste size={13} /> Paste here (Ctrl+V)
          </button>
          <button className="btn btn-secondary btn-sm w-full" onClick={applyAll}
            title="Apply the copied type, pane, grill and hardware to every region of the same type">
            <Layers size={13} /> Apply to all {clipboard.regionType} regions
          </button>
        </>
      )}
    </div>
  )
}

export default function PropertiesPanel() {
  const tree = useEditorStore((s) => s.tree)
  const selectedId = useEditorStore((s) => s.selectedId)
  const updateRegion = useEditorStore((s) => s.updateRegion)
  const collapseRegion = useEditorStore((s) => s.collapseRegion)
  const deselect = useEditorStore((s) => s.deselect)
  const setFrameSize = useEditorStore((s) => s.setFrameSize)

  if (!tree) return null

  const selected = selectedId ? findRegion(tree.frame.rootRegion, selectedId) : null

  if (!selected) {
    return (
      <div>
        <div className="panel-section">
          <div className="panel-title">Design Info</div>
          <div className="flex gap-3">
            <div className="form-group" style={{ flex: 1 }}>
              <label>Width</label>
              <DimensionInput
                value={tree.outerWidth}
                onCommit={(v) => setFrameSize(v, tree.outerHeight, { history: true })}
                title={'Decimal feet or ft-in (e.g. 5\'6") — snaps to 3"'}
              />
            </div>
            <div className="form-group" style={{ flex: 1 }}>
              <label>Height</label>
              <DimensionInput
                value={tree.outerHeight}
                onCommit={(v) => setFrameSize(tree.outerWidth, v, { history: true })}
                title={'Decimal feet or ft-in (e.g. 4\'6") — snaps to 3"'}
              />
            </div>
          </div>
          <div className="flex justify-between" style={{ fontSize: '0.875rem', marginTop: 4 }}>
            <span className="text-muted">Section</span>
            <span className="font-mono">{tree.sectionSize}" {tree.gauge}</span>
          </div>
        </div>
        <div className="panel-section">
          <p className="text-xs text-muted" style={{ lineHeight: 1.6 }}>
            Click a region on the canvas to select it and edit its properties.
            Click a mullion to set its exact position.
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
          <div className="panel-title">{selected.isLeaf ? 'Selected Region' : 'Selected Split'}</div>
          <button className="btn btn-ghost btn-icon" style={{ padding: 2 }} onClick={deselect}>
            <X size={14} />
          </button>
        </div>
        <div style={{ fontSize: '0.8125rem', color: 'var(--c-text-muted)', fontFamily: 'var(--font-mono)' }}>
          {fmtFtIn(selected.height)} × {fmtFtIn(selected.width)}
        </div>
      </div>

      {/* Exact mullion/transom position (branch only) */}
      {!selected.isLeaf && selected.split && (
        <div className="panel-section">
          <div className="panel-title">{selected.split.direction === 'vertical' ? 'Mullion Position' : 'Transom Position'}</div>
          <SplitPositionEditor region={selected} />
        </div>
      )}

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
                  // §10.3 steps 2–3: switching TO shutter/door auto-adds hinges (R-4/R-5).
                  hardware: rt.value === 'shutter' || rt.value === 'door'
                    ? [{
                        id: crypto.randomUUID(), type: 'hardware', hardwareType: 'hinge', variant: 'SS_12G',
                        quantity: (rt.value === 'door' ? doorHingeCount : windowHingeCount)(selected.height),
                        autoComputed: true, side: 'front',
                      }]
                    : [],
                  doorHand: null,
                  rebate: 'single',
                  // §10.3 step 5: the grill survives only on fixed/shutter — an open
                  // void or louver carries no grill, and a door never does (§4A.2).
                  ...(rt.value === 'fixed' || rt.value === 'shutter' ? {} : { overlays: [] }),
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

      {/* Copy / paste / bulk apply */}
      {selected.isLeaf && (
        <div className="panel-section">
          <div className="panel-title">Copy &amp; Paste</div>
          <ClipboardSection region={selected} />
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
