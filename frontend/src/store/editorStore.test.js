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
