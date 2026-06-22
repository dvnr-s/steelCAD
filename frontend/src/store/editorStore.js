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
})

// A new design tree skeleton
export const makeEmptyTree = (name, width, height, sectionSize = '5', gauge = '18G') => ({
  id: crypto.randomUUID(),
  type: 'design',
  name,
  outerWidth: width,
  outerHeight: height,
  sectionSize,
  gauge,
  frame: {
    id: crypto.randomUUID(),
    type: 'frame',
    width,
    height,
    rootRegion: makeLeafRegion(0, 0, width, height),
  },
})

const useEditorStore = create((set, get) => ({
  // The active design tree (DesignTree schema)
  tree: null,
  designId: null,
  designName: '',
  isDirty: false,

  // Selection
  selectedId: null,

  // Live pricing from backend (null = not loaded yet)
  livePrice: null,

  // ─── Tree management ────────────────────────────────────
  initTree: (designId, tree) =>
    set({ tree, designId, designName: tree.name, isDirty: false, selectedId: null }),

  newTree: (name, width, height, sectionSize, gauge) => {
    const tree = makeEmptyTree(name, width, height, sectionSize, gauge)
    set({ tree, designId: null, designName: name, isDirty: true, selectedId: null })
  },

  setTree: (tree) => set({ tree, isDirty: true }),

  markSaved: (designId) => set({ designId, isDirty: false }),

  // ─── Selection ──────────────────────────────────────────
  select: (id) => set({ selectedId: id }),
  deselect: () => set({ selectedId: null }),

  // ─── Region operations ──────────────────────────────────

  /**
   * Split a region by ID. direction = 'vertical' | 'horizontal', position = 0..1
   */
  splitRegion: (regionId, direction, position = 0.5) => {
    const tree = get().tree
    if (!tree) return
    const newTree = _splitRegionInTree(tree, regionId, direction, position)
    set({ tree: newTree, isDirty: true, selectedId: null })
  },

  /**
   * Update a leaf region's properties (regionType, paneSpec, overlays, hardware)
   */
  updateRegion: (regionId, patch) => {
    const tree = get().tree
    if (!tree) return
    const newTree = _updateRegionInTree(tree, regionId, patch)
    set({ tree: newTree, isDirty: true })
  },

  /**
   * Remove all children of a branch region, making it a leaf again.
   */
  collapseRegion: (regionId) => {
    const tree = get().tree
    if (!tree) return
    const newTree = _collapseRegionInTree(tree, regionId)
    set({ tree: newTree, isDirty: true, selectedId: regionId })
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
    return { ...region, isLeaf: true, regionType: 'open', split: null, hardware: [], paneSpec: null, overlays: [] }
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
