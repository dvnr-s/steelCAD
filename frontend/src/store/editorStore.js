/**
 * Zustand store — Design editor state
 * Owns the canvas tree, selection, and live pricing preview.
 */
import { create } from 'zustand'

// A fresh empty leaf region at given dims
export const makeLeafRegion = (x, y, w, h) => ({
  id: crypto.randomUUID(),
  type: 'region',
  x, y, width: w, height: h,
  isLeaf: true,
  regionType: 'open',
  paneSpec: null,
  overlays: [],
  hardware: [],
  split: null,
  doorHand: null,        // door-region label only (spec §4A.4)
  rebate: 'single',      // door-region rebate (spec §4A.5)
})

// Door hinge auto-count by leaf height (spec R-5 / §4A): ≤7ft→3, ≤8ft→4, else 5.
export const doorHingeCount = (height) => (height <= 7 ? 3 : height <= 8 ? 4 : 5)

// A door leaf pre-typed as a door (used to seed a standalone door product).
// A door has NO pane/grill (§4A.2) — only hardware (hinges/lock) + hand/rebate.
export const makeDoorRegion = (x, y, w, h) => ({
  ...makeLeafRegion(x, y, w, h),
  regionType: 'door',
  paneSpec: null,
  hardware: [
    { id: crypto.randomUUID(), type: 'hardware', hardwareType: 'hinge', variant: 'SS_12G', quantity: doorHingeCount(h), autoComputed: true, side: 'front' },
  ],
})

// A new design tree skeleton. productType "door" seeds a pre-typed door leaf.
export const makeEmptyTree = (name, width, height, sectionSize = '5', gauge = '18G', productType = 'window') => ({
  id: crypto.randomUUID(),
  type: 'design',
  name,
  productType,
  outerWidth: width,
  outerHeight: height,
  sectionSize,
  gauge,
  frame: {
    id: crypto.randomUUID(),
    type: 'frame',
    width,
    height,
    rootRegion: productType === 'door'
      ? makeDoorRegion(0, 0, width, height)
      : makeLeafRegion(0, 0, width, height),
  },
})

// Max number of undo steps retained in memory.
const HISTORY_LIMIT = 50

// Layout / snapping constants (in feet).
export const GRID = 0.25      // 3-inch snap increment
export const MIN_SIDE = 0.5   // smallest allowed region edge
const FRAME_MIN = 1
const FRAME_MAX = 30

/**
 * Snap a split's offset to the grid and clamp it so each side keeps MIN_SIDE.
 * `size` is the parent region's length along the split axis (ft); `position`
 * is the desired ratio (0..1). Returns the snapped/clamped ratio.
 */
export function snapOffset(size, position) {
  if (size <= 2 * MIN_SIDE) return 0.5
  let offset = Math.round((size * position) / GRID) * GRID
  offset = Math.max(MIN_SIDE, Math.min(size - MIN_SIDE, offset))
  return offset / size
}

const snapFrame = (v) => Math.max(FRAME_MIN, Math.min(FRAME_MAX, Math.round(v / GRID) * GRID))

/** Find a region node by id within a region subtree. */
export function findRegionNode(region, id) {
  if (region.id === id) return region
  if (region.split) {
    for (const c of region.split.children) {
      const found = findRegionNode(c, id)
      if (found) return found
    }
  }
  return null
}

/**
 * Re-derive x/y/width/height for every region from the frame size and each
 * split's position. This is the single source of truth for geometry — any
 * drag just updates a split position (or the frame size) and calls relayout.
 */
export function relayout(tree) {
  if (!tree?.frame) return tree
  const root = _layoutRegion(tree.frame.rootRegion, 0, 0, tree.frame.width, tree.frame.height)
  return { ...tree, frame: { ...tree.frame, rootRegion: root } }
}

function _layoutRegion(region, x, y, w, h) {
  const base = { ...region, x, y, width: w, height: h }
  if (region.isLeaf || !region.split) return base
  const { direction, position } = region.split
  const [a, b] = region.split.children
  let ca, cb
  if (direction === 'vertical') {
    ca = _layoutRegion(a, x, y, w * position, h)
    cb = _layoutRegion(b, x + w * position, y, w * (1 - position), h)
  } else {
    ca = _layoutRegion(a, x, y, w, h * position)
    cb = _layoutRegion(b, x, y + h * position, w, h * (1 - position))
  }
  return { ...base, split: { ...region.split, children: [ca, cb] } }
}

/** Immutably apply `fn` to the region matching `regionId`. */
function _mapRegionInTree(tree, regionId, fn) {
  return {
    ...tree,
    frame: { ...tree.frame, rootRegion: _mapRegionNode(tree.frame.rootRegion, regionId, fn) },
  }
}

function _mapRegionNode(region, id, fn) {
  if (region.id === id) return fn(region)
  if (region.split) {
    return {
      ...region,
      split: { ...region.split, children: region.split.children.map((c) => _mapRegionNode(c, id, fn)) },
    }
  }
  return region
}

const useEditorStore = create((set, get) => ({
  // The active design tree (DesignTree schema)
  tree: null,
  designId: null,
  designName: '',
  isDirty: false,

  // Undo/redo history — snapshots of the tree before each mutation.
  past: [],
  future: [],

  // Selection
  selectedId: null,

  // Active canvas tool: null | 'vertical' | 'horizontal' (drag-to-add mullion)
  addMode: null,
  setAddMode: (addMode) => set({ addMode }),

  // Snapshot taken at the start of a drag, used to record one undo step on release.
  _snapshot: null,

  // Live pricing from backend (null = not loaded yet)
  livePrice: null,

  // ─── Tree management ────────────────────────────────────
  initTree: (designId, tree) =>
    set({ tree, designId, designName: tree.name, isDirty: false, selectedId: null, past: [], future: [] }),

  newTree: (name, width, height, sectionSize, gauge) => {
    const tree = makeEmptyTree(name, width, height, sectionSize, gauge)
    set({ tree, designId: null, designName: name, isDirty: true, selectedId: null, past: [], future: [] })
  },

  setTree: (tree) => set({ tree, isDirty: true }),

  markSaved: (designId) => set({ designId, isDirty: false }),

  /**
   * Commit a new tree, pushing the current one onto the undo stack and
   * clearing the redo stack. All mutating actions route through this.
   */
  _commit: (newTree, extra = {}) => {
    const { tree, past } = get()
    set({
      tree: newTree,
      past: tree ? [...past, tree].slice(-HISTORY_LIMIT) : past,
      future: [],
      isDirty: true,
      ...extra,
    })
  },

  // ─── Undo / redo ────────────────────────────────────────
  undo: () => {
    const { past, future, tree } = get()
    if (past.length === 0) return
    const previous = past[past.length - 1]
    set({
      tree: previous,
      past: past.slice(0, -1),
      future: tree ? [tree, ...future].slice(0, HISTORY_LIMIT) : future,
      isDirty: true,
      selectedId: null,
    })
  },

  redo: () => {
    const { past, future, tree } = get()
    if (future.length === 0) return
    const next = future[0]
    set({
      tree: next,
      past: tree ? [...past, tree].slice(-HISTORY_LIMIT) : past,
      future: future.slice(1),
      isDirty: true,
      selectedId: null,
    })
  },

  // ─── Selection ──────────────────────────────────────────
  select: (id) => set({ selectedId: id }),
  deselect: () => set({ selectedId: null }),

  // ─── Region operations ──────────────────────────────────

  /**
   * Split a region by ID. direction = 'vertical' | 'horizontal', position = 0..1
   */
  splitRegion: (regionId, direction, position = 0.5) => {
    const { tree } = get()
    if (!tree) return
    const region = findRegionNode(tree.frame.rootRegion, regionId)
    if (!region || !region.isLeaf) return
    const axis = direction === 'vertical' ? region.width : region.height
    const pos = snapOffset(axis, position)
    const newTree = relayout(_splitRegionInTree(tree, regionId, direction, pos))
    get()._commit(newTree, { selectedId: null })
  },

  /**
   * Reposition an existing split (drag a mullion). With history:false this is a
   * live preview during a drag; pair it with beginInteraction/endInteraction so
   * the whole drag collapses into a single undo step.
   */
  setSplitPosition: (regionId, rawPosition, { history = false } = {}) => {
    const { tree } = get()
    if (!tree) return
    const region = findRegionNode(tree.frame.rootRegion, regionId)
    if (!region?.split) return
    const axis = region.split.direction === 'vertical' ? region.width : region.height
    const position = snapOffset(axis, rawPosition)
    const laid = relayout(
      _mapRegionInTree(tree, regionId, (r) => ({ ...r, split: { ...r.split, position } }))
    )
    if (history) get()._commit(laid)
    else set({ tree: laid, isDirty: true })
  },

  /** Resize the outer frame (drag a frame handle). Same live/commit pattern. */
  setFrameSize: (rawW, rawH, { history = false } = {}) => {
    const { tree } = get()
    if (!tree) return
    const width = snapFrame(rawW)
    const height = snapFrame(rawH)
    const laid = relayout({
      ...tree,
      outerWidth: width,
      outerHeight: height,
      frame: { ...tree.frame, width, height },
    })
    if (history) get()._commit(laid)
    else set({ tree: laid, isDirty: true })
  },

  // ─── Drag lifecycle ─────────────────────────────────────
  // Capture the pre-drag tree; record one undo step on release if it changed.
  beginInteraction: () => {
    if (get()._snapshot == null) set({ _snapshot: get().tree })
  },
  endInteraction: () => {
    const { _snapshot, tree, past } = get()
    if (_snapshot && _snapshot !== tree) {
      set({
        past: [...past, _snapshot].slice(-HISTORY_LIMIT),
        future: [],
        _snapshot: null,
        isDirty: true,
      })
    } else {
      set({ _snapshot: null })
    }
  },

  /**
   * Update a leaf region's properties (regionType, paneSpec, overlays, hardware)
   */
  updateRegion: (regionId, patch) => {
    const tree = get().tree
    if (!tree) return
    const newTree = _updateRegionInTree(tree, regionId, patch)
    get()._commit(newTree)
  },

  /**
   * Remove all children of a branch region, making it a leaf again.
   */
  collapseRegion: (regionId) => {
    const tree = get().tree
    if (!tree) return
    const newTree = _collapseRegionInTree(tree, regionId)
    get()._commit(newTree, { selectedId: regionId })
  },

  // ─── Live price ─────────────────────────────────────────
  setLivePrice: (livePrice) => set({ livePrice }),
}))

export default useEditorStore


// ─── Pure tree mutation helpers ────────────────────────────────────

function _splitRegionInTree(tree, regionId, direction, position) {
  return {
    ...tree,
    frame: {
      ...tree.frame,
      rootRegion: _splitRegionNode(tree.frame.rootRegion, regionId, direction, position),
    },
  }
}

function _splitRegionNode(region, targetId, direction, position) {
  if (region.id === targetId && region.isLeaf) {
    const { width: w, height: h, x, y } = region
    let childA, childB
    if (direction === 'vertical') {
      childA = makeLeafRegion(x, y, w * position, h)
      childB = makeLeafRegion(x + w * position, y, w * (1 - position), h)
    } else {
      childA = makeLeafRegion(x, y, w, h * position)
      childB = makeLeafRegion(x, y + h * position, w, h * (1 - position))
    }
    return {
      ...region,
      isLeaf: false,
      regionType: null,
      paneSpec: null,
      hardware: [],
      doorHand: null,        // shed door labels — this is no longer a door leaf
      rebate: 'single',
      split: {
        id: crypto.randomUUID(),
        type: 'split',
        direction,
        position,
        children: [childA, childB],
      },
    }
  }
  if (region.split) {
    return {
      ...region,
      split: {
        ...region.split,
        children: region.split.children.map((c) =>
          _splitRegionNode(c, targetId, direction, position)
        ),
      },
    }
  }
  return region
}

function _updateRegionInTree(tree, regionId, patch) {
  return {
    ...tree,
    frame: {
      ...tree.frame,
      rootRegion: _updateRegionNode(tree.frame.rootRegion, regionId, patch),
    },
  }
}

function _updateRegionNode(region, targetId, patch) {
  if (region.id === targetId) return { ...region, ...patch }
  if (region.split) {
    return {
      ...region,
      split: {
        ...region.split,
        children: region.split.children.map((c) => _updateRegionNode(c, targetId, patch)),
      },
    }
  }
  return region
}

function _collapseRegionInTree(tree, regionId) {
  return {
    ...tree,
    frame: {
      ...tree.frame,
      rootRegion: _collapseRegionNode(tree.frame.rootRegion, regionId),
    },
  }
}

function _collapseRegionNode(region, targetId) {
  if (region.id === targetId) {
    return { ...region, isLeaf: true, regionType: 'open', split: null, hardware: [], paneSpec: null, overlays: [], doorHand: null, rebate: 'single' }
  }
  if (region.split) {
    return {
      ...region,
      split: {
        ...region.split,
        children: region.split.children.map((c) => _collapseRegionNode(c, targetId)),
      },
    }
  }
  return region
}
