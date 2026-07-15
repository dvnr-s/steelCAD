/**
 * editorStore mutation / undo-redo invariants.
 * The store is a module-level singleton — each test re-seeds it with newTree.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import useEditorStore, { makeEmptyTree, listLeafIds, doorHingeCount } from './editorStore'

const store = () => useEditorStore.getState()

const seed = (width = 5, height = 4) => {
  store().newTree('Test', width, height, '5', '18G')
  return store().tree
}

beforeEach(() => {
  useEditorStore.setState({
    tree: null, designId: null, past: [], future: [],
    selectedId: null, clipboard: null, addMode: null, _snapshot: null, livePrice: null,
  })
})

describe('makeEmptyTree product defaults', () => {
  it('window seeds a single open leaf', () => {
    const t = makeEmptyTree('W', 5, 4, '5', '18G', 'window')
    expect(t.productType).toBe('window')
    expect(t.frame.rootRegion.regionType).toBe('open')
    expect(t.frame.rootRegion.hardware).toEqual([])
  })

  it('door seeds a door leaf with auto hinges by height', () => {
    const t = makeEmptyTree('D', 3.5, 7, '5', '18G', 'door')
    const root = t.frame.rootRegion
    expect(root.regionType).toBe('door')
    expect(root.hardware).toHaveLength(1)
    expect(root.hardware[0].hardwareType).toBe('hinge')
    expect(root.hardware[0].quantity).toBe(3) // ≤7ft → 3
    expect(doorHingeCount(8)).toBe(4)
    expect(doorHingeCount(9)).toBe(5)
  })
})

describe('splitRegion / collapseRegion', () => {
  it('splits a leaf into two laid-out children', () => {
    const t = seed(5, 4)
    const rootId = t.frame.rootRegion.id
    store().splitRegion(rootId, 'vertical', 0.5)

    const root = store().tree.frame.rootRegion
    expect(root.isLeaf).toBe(false)
    expect(root.split.direction).toBe('vertical')
    const [a, b] = root.split.children
    expect(a.width).toBeCloseTo(2.5)
    expect(b.width).toBeCloseTo(2.5)
    expect(a.x).toBe(0)
    expect(b.x).toBeCloseTo(2.5)
    expect(store().past).toHaveLength(1) // one undo step
  })

  it('snaps the split position to the grid and MIN_SIDE clamp', () => {
    const t = seed(5, 4)
    store().splitRegion(t.frame.rootRegion.id, 'vertical', 0.01)
    const [a] = store().tree.frame.rootRegion.split.children
    expect(a.width).toBeCloseTo(0.5) // clamped to MIN_SIDE
  })

  it('collapse makes the branch a leaf again and selects it', () => {
    const t = seed(5, 4)
    const rootId = t.frame.rootRegion.id
    store().splitRegion(rootId, 'horizontal', 0.5)
    store().collapseRegion(rootId)
    expect(store().tree.frame.rootRegion.isLeaf).toBe(true)
    expect(store().selectedId).toBe(rootId)
  })
})

describe('grill overlays across split / collapse (spec R-3, §10.1–10.2)', () => {
  const grill = (material, barAdjust = 0) => ({
    id: crypto.randomUUID(), type: 'overlay', overlayType: 'grill', material,
    config: barAdjust ? { barAdjust } : {},
  })

  it('split preserves an SS grill as a continuity overlay (delta carried)', () => {
    const t = seed(5, 4)
    const rootId = t.frame.rootRegion.id
    store().updateRegion(rootId, { regionType: 'fixed', overlays: [grill('SS_PIPE_ROUND', 2)] })
    store().splitRegion(rootId, 'vertical', 0.5)

    const root = store().tree.frame.rootRegion
    expect(root.isLeaf).toBe(false)
    expect(root.overlays).toHaveLength(1)
    expect(root.overlays[0].material).toBe('SS_PIPE_ROUND')
    expect(root.overlays[0].config.is_continuity).toBe(true)
    expect(root.overlays[0].config.barAdjust).toBe(2)
  })

  it('split removes an MS grill (never legal on a branch)', () => {
    const t = seed(5, 4)
    const rootId = t.frame.rootRegion.id
    store().updateRegion(rootId, { regionType: 'fixed', overlays: [grill('MS_SQUARE')] })
    store().splitRegion(rootId, 'vertical', 0.5)
    expect(store().tree.frame.rootRegion.overlays).toEqual([])
  })

  it('collapse keeps the SS continuity grill on the resulting leaf', () => {
    const t = seed(5, 4)
    const rootId = t.frame.rootRegion.id
    store().updateRegion(rootId, { regionType: 'fixed', overlays: [grill('SS_PIPE_SQUARE')] })
    store().splitRegion(rootId, 'horizontal', 0.5)
    store().collapseRegion(rootId)

    const root = store().tree.frame.rootRegion
    expect(root.isLeaf).toBe(true)
    expect(root.regionType).toBe('open')
    expect(root.overlays).toHaveLength(1)
    expect(root.overlays[0].material).toBe('SS_PIPE_SQUARE')
    expect(root.overlays[0].config.is_continuity).toBe(false)
  })

  it('initTree strips MS grills stranded on branches by the old split bug', () => {
    const t = seed(5, 4)
    const rootId = t.frame.rootRegion.id
    store().splitRegion(rootId, 'vertical', 0.5)
    store().updateRegion(rootId, { overlays: [grill('MS_SQUARE')] }) // simulate legacy data
    const dirtyTree = store().tree

    store().initTree('design-1', dirtyTree)
    expect(store().tree.frame.rootRegion.overlays).toEqual([])
    expect(store().isDirty).toBe(true) // repaired → wants saving back
  })
})

describe('auto-computed hinges track height changes (spec §10.8–10.9)', () => {
  const hinge = (quantity, autoComputed = true) => ({
    id: crypto.randomUUID(), type: 'hardware', hardwareType: 'hinge',
    variant: 'SS_12G', quantity, autoComputed, side: 'front',
  })

  it('frame resize recomputes autoComputed door hinge quantity', () => {
    const t = seed(3.5, 7)
    const rootId = t.frame.rootRegion.id
    store().updateRegion(rootId, { regionType: 'door', hardware: [hinge(doorHingeCount(7))] })
    expect(store().tree.frame.rootRegion.hardware[0].quantity).toBe(3)

    store().setFrameSize(3.5, 9, { history: true })
    expect(store().tree.frame.rootRegion.hardware[0].quantity).toBe(5) // >8ft → 5
  })

  it('frame resize leaves user-overridden quantities alone', () => {
    const t = seed(3.5, 7)
    const rootId = t.frame.rootRegion.id
    store().updateRegion(rootId, { regionType: 'door', hardware: [hinge(2, false)] })
    store().setFrameSize(3.5, 9, { history: true })
    expect(store().tree.frame.rootRegion.hardware[0].quantity).toBe(2)
  })

  it('moving a transom recomputes the shutter hinge count', () => {
    const t = seed(5, 8)
    const rootId = t.frame.rootRegion.id
    store().splitRegion(rootId, 'horizontal', 0.5)
    const [, bottomId] = listLeafIds(store().tree)
    store().updateRegion(bottomId, { regionType: 'shutter', hardware: [hinge(2)] }) // h=4 → 2

    store().setSplitPosition(rootId, 0.1875, { history: true }) // bottom becomes 6.5ft
    const bottom = store().tree.frame.rootRegion.split.children[1]
    expect(bottom.height).toBeCloseTo(6.5)
    expect(bottom.hardware[0].quantity).toBe(3) // ≤7ft → 3
  })
})

describe('setFrameSize', () => {
  it('snaps to the grid and relayouts children', () => {
    const t = seed(5, 4)
    store().splitRegion(t.frame.rootRegion.id, 'vertical', 0.5)
    store().setFrameSize(6.1, 4, { history: true })
    const tree = store().tree
    expect(tree.frame.width).toBe(6)          // 0.25ft grid snap
    const [a, b] = tree.frame.rootRegion.split.children
    expect(a.width + b.width).toBeCloseTo(6)  // children re-derived
  })

  it('clamps to the frame bounds', () => {
    seed(5, 4)
    store().setFrameSize(99, 0.1, { history: true })
    expect(store().tree.frame.width).toBe(30)
    expect(store().tree.frame.height).toBe(1)
  })
})

describe('undo / redo', () => {
  it('round-trips a split', () => {
    const t = seed(5, 4)
    store().splitRegion(t.frame.rootRegion.id, 'vertical', 0.5)
    expect(store().tree.frame.rootRegion.isLeaf).toBe(false)

    store().undo()
    expect(store().tree.frame.rootRegion.isLeaf).toBe(true)
    expect(store().future).toHaveLength(1)

    store().redo()
    expect(store().tree.frame.rootRegion.isLeaf).toBe(false)
    expect(store().future).toHaveLength(0)
  })

  it('a new mutation clears the redo stack', () => {
    const t = seed(5, 4)
    const rootId = t.frame.rootRegion.id
    store().splitRegion(rootId, 'vertical', 0.5)
    store().undo()
    store().splitRegion(rootId, 'horizontal', 0.5)
    expect(store().future).toHaveLength(0)
    store().redo() // no-op
    expect(store().tree.frame.rootRegion.split.direction).toBe('horizontal')
  })

  it('undo is a no-op with no history', () => {
    const t = seed(5, 4)
    store().undo()
    expect(store().tree).toBe(t)
  })
})

describe('copy / paste', () => {
  it('copies a leaf spec onto another leaf with fresh attachment ids', () => {
    const t = seed(5, 4)
    store().splitRegion(t.frame.rootRegion.id, 'vertical', 0.5)
    const [aId, bId] = listLeafIds(store().tree)

    store().updateRegion(aId, {
      regionType: 'shutter',
      paneSpec: { shutterMaterial: 'MS_PIPE', infillType: 'glass', hasBeading: true },
      hardware: [{ id: 'hw-1', type: 'hardware', hardwareType: 'hinge', variant: 'SS_12G', quantity: 2, autoComputed: true, side: 'front' }],
    })
    expect(store().copyRegion(aId)).toBe(true)
    expect(store().pasteOnto(bId)).toBe(true)

    const b = store().tree.frame.rootRegion.split.children[1]
    expect(b.regionType).toBe('shutter')
    expect(b.paneSpec).toEqual({ shutterMaterial: 'MS_PIPE', infillType: 'glass', hasBeading: true })
    expect(b.hardware).toHaveLength(1)
    expect(b.hardware[0].id).not.toBe('hw-1') // regenerated id
  })

  it('copy fails on a branch region', () => {
    const t = seed(5, 4)
    const rootId = t.frame.rootRegion.id
    store().splitRegion(rootId, 'vertical', 0.5)
    expect(store().copyRegion(rootId)).toBe(false)
  })

  it('paste without a clipboard is a no-op', () => {
    const t = seed(5, 4)
    expect(store().pasteOnto(t.frame.rootRegion.id)).toBe(false)
  })
})

describe('pasteOntoAllSimilar', () => {
  // 4 leaves: [fixed(source), fixed, shutter, fixed]
  const seedQuad = () => {
    const t = seed(8, 4)
    store().splitRegion(t.frame.rootRegion.id, 'vertical', 0.5)
    const [aId, bId] = listLeafIds(store().tree)
    store().splitRegion(aId, 'vertical', 0.5)
    store().splitRegion(bId, 'vertical', 0.5)
    const leaves = listLeafIds(store().tree)
    leaves.forEach((id, i) => store().updateRegion(id, { regionType: i === 2 ? 'shutter' : 'fixed' }))
    return leaves
  }

  it('applies the copied spec to every leaf of the same type in one undo step', () => {
    const leaves = seedQuad()
    store().updateRegion(leaves[0], {
      paneSpec: { shutterMaterial: null, infillType: 'glass', hasBeading: true },
    })
    expect(store().copyRegion(leaves[0])).toBe(true)

    const before = store().past.length
    expect(store().pasteOntoAllSimilar()).toBe(3) // the 3 fixed leaves (incl. source)
    expect(store().past.length).toBe(before + 1)  // single undo step

    const spec = (id) => {
      const walk = (r) => (r.id === id ? r : (r.split?.children.map(walk).find(Boolean) ?? null))
      return walk(store().tree.frame.rootRegion)
    }
    for (const i of [0, 1, 3]) {
      expect(spec(leaves[i]).regionType).toBe('fixed')
      expect(spec(leaves[i]).paneSpec).toEqual({ shutterMaterial: null, infillType: 'glass', hasBeading: true })
    }
    // The shutter leaf is untouched.
    expect(spec(leaves[2]).regionType).toBe('shutter')
    expect(spec(leaves[2]).paneSpec).toBeNull()
  })

  it('returns 0 without a clipboard', () => {
    seedQuad()
    expect(store().pasteOntoAllSimilar()).toBe(0)
  })

  it('regenerates hardware ids per target', () => {
    const leaves = seedQuad()
    store().updateRegion(leaves[0], {
      hardware: [{ id: 'hw-1', type: 'hardware', hardwareType: 'hinge', variant: 'SS_12G', quantity: 2, autoComputed: false, side: 'front' }],
    })
    store().copyRegion(leaves[0])
    store().pasteOntoAllSimilar()
    const walk = (r, acc) => {
      if (r.isLeaf) { acc.push(r); return acc }
      r.split.children.forEach((c) => walk(c, acc))
      return acc
    }
    const fixed = walk(store().tree.frame.rootRegion, []).filter((r) => r.regionType === 'fixed')
    const ids = fixed.flatMap((r) => r.hardware.map((h) => h.id))
    expect(ids).toHaveLength(3)
    expect(new Set(ids).size).toBe(3) // all distinct
  })
})
