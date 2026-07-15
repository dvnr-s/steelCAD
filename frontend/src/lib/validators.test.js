import { describe, it, expect } from 'vitest'
import { validateTree } from './validators'

// ── Helpers ──────────────────────────────────────────────────────

function leafRegion(overrides = {}) {
  return {
    id: 'r1',
    isLeaf: true,
    width: 2,
    height: 2,
    regionType: 'fixed',
    paneSpec: {},
    hardware: [],
    overlays: [],
    ...overrides,
  }
}

function tree(regionOverrides = {}, frameOverrides = {}) {
  return {
    frame: {
      id: 'f1',
      width: 4,
      height: 3,
      rootRegion: leafRegion(regionOverrides),
      ...frameOverrides,
    }
  }
}

// ── Tests ─────────────────────────────────────────────────────────

describe('validateTree', () => {
  it('returns no issues for a valid fixed region', () => {
    expect(validateTree(tree())).toEqual([])
  })

  it('returns an error when tree is null', () => {
    const issues = validateTree(null)
    expect(issues.length).toBeGreaterThan(0)
  })

  it('returns frame-size error when frame is below 1ft', () => {
    const issues = validateTree(tree({}, { width: 0.5, height: 0.5 }))
    expect(issues.some(i => i.message.includes('at least 1ft'))).toBe(true)
  })

  it('returns error when leaf has no region type', () => {
    const issues = validateTree(tree({ regionType: undefined }))
    expect(issues.some(i => i.message.includes('needs a type'))).toBe(true)
  })

  it('returns error when region is below minimum dimension', () => {
    const issues = validateTree(tree({ width: 0.4 }))
    expect(issues.some(i => i.message.includes('0.5ft minimum'))).toBe(true)
  })

  it('returns error for shutter without material', () => {
    const issues = validateTree(tree({ regionType: 'shutter', paneSpec: {}, hardware: [{ hardwareType: 'hinge' }] }))
    expect(issues.some(i => i.message.includes('shutter material'))).toBe(true)
  })

  it('returns error for shutter without a hinge', () => {
    const issues = validateTree(tree({
      regionType: 'shutter',
      paneSpec: { shutterMaterial: 'MS_PIPE' },
      hardware: [],
    }))
    expect(issues.some(i => i.message.includes('hinge'))).toBe(true)
  })

  it('returns error for lock on a non-door region', () => {
    const issues = validateTree(tree({
      regionType: 'fixed',
      hardware: [{ hardwareType: 'lock' }],
    }))
    expect(issues.some(i => i.message.includes('locks are door-only'))).toBe(true)
  })

  it('returns error for door region with pane spec', () => {
    const issues = validateTree(tree({
      regionType: 'door',
      paneSpec: { shutterMaterial: 'MS_PIPE' },
      hardware: [{ hardwareType: 'hinge' }],
    }))
    expect(issues.some(i => i.message.includes('no pane'))).toBe(true)
  })

  it('returns error for door region with a grill overlay', () => {
    const issues = validateTree(tree({
      regionType: 'door',
      paneSpec: {},
      hardware: [{ hardwareType: 'hinge' }],
      overlays: [{ material: 'MS_SQUARE' }],
    }))
    expect(issues.some(i => i.message.includes('cannot have a grill'))).toBe(true)
  })

  it('returns error for beading without infill', () => {
    const issues = validateTree(tree({
      regionType: 'fixed',
      paneSpec: { hasBeading: true, infillType: 'none' },
    }))
    expect(issues.some(i => i.message.includes('glass or jali infill'))).toBe(true)
  })

  it('returns error for grill overlay without material', () => {
    const issues = validateTree(tree({
      regionType: 'fixed',
      overlays: [{ material: undefined }],
    }))
    expect(issues.some(i => i.message.includes('needs a material'))).toBe(true)
  })

  it('returns error for back-side hardware on non-double-rebate door', () => {
    const issues = validateTree(tree({
      regionType: 'door',
      rebate: 'single',
      paneSpec: {},
      hardware: [{ hardwareType: 'hinge' }, { hardwareType: 'hinge', side: 'back' }],
    }))
    expect(issues.some(i => i.message.includes('double-rebate'))).toBe(true)
  })

  it('returns no issues for valid door with double-rebate back hardware', () => {
    const issues = validateTree(tree({
      regionType: 'door',
      rebate: 'double',
      paneSpec: {},
      hardware: [
        { hardwareType: 'hinge' },
        { hardwareType: 'hinge', side: 'back' },
      ],
      overlays: [],
    }))
    expect(issues).toEqual([])
  })

  it('returns no issues for a valid double shutter (glass + jali)', () => {
    const issues = validateTree(tree({
      regionType: 'shutter',
      paneSpec: { shutterConfig: 'double', shutterMaterial: 'MS_PIPE', infillType: 'glass', jaliMaterial: 'MS_PIPE' },
      hardware: [{ hardwareType: 'hinge' }, { hardwareType: 'hinge', side: 'back' }],
    }))
    expect(issues).toEqual([])
  })

  it('returns error for double shutter without a jali-side material', () => {
    const issues = validateTree(tree({
      regionType: 'shutter',
      paneSpec: { shutterConfig: 'double', shutterMaterial: 'MS_PIPE', infillType: 'glass' },
      hardware: [{ hardwareType: 'hinge' }, { hardwareType: 'hinge', side: 'back' }],
    }))
    expect(issues.some(i => i.message.includes('jali-side material'))).toBe(true)
  })

  it('returns error for double shuttering on a fixed region', () => {
    const issues = validateTree(tree({
      regionType: 'fixed',
      paneSpec: { shutterConfig: 'double', infillType: 'glass', jaliMaterial: 'MS_PIPE' },
    }))
    expect(issues.some(i => i.message.includes('only shutter regions'))).toBe(true)
  })

  it('returns error for jali-side fields on a single shutter', () => {
    const issues = validateTree(tree({
      regionType: 'shutter',
      paneSpec: { shutterMaterial: 'MS_PIPE', infillType: 'glass', jaliMaterial: 'MS_PIPE' },
      hardware: [{ hardwareType: 'hinge' }],
    }))
    expect(issues.some(i => i.message.includes('require double shuttering'))).toBe(true)
  })

  it('returns error for double shutter missing a hinge on one side', () => {
    const issues = validateTree(tree({
      regionType: 'shutter',
      paneSpec: { shutterConfig: 'double', shutterMaterial: 'MS_PIPE', infillType: 'glass', jaliMaterial: 'MS_PIPE' },
      hardware: [{ hardwareType: 'hinge' }],
    }))
    expect(issues.some(i => i.message.includes('hinge on each side'))).toBe(true)
  })

  // ── Customer-supplied shutter (HINGES_ONLY, §5.8) ──
  it('returns no issues for a single HINGES_ONLY shutter (hinges only)', () => {
    const issues = validateTree(tree({
      regionType: 'shutter',
      paneSpec: { shutterMaterial: 'HINGES_ONLY', infillType: 'none' },
      hardware: [{ hardwareType: 'hinge' }],
    }))
    expect(issues).toEqual([])
  })

  it('returns no issues for a double HINGES_ONLY shutter (exempt from V-19)', () => {
    const issues = validateTree(tree({
      regionType: 'shutter',
      paneSpec: { shutterConfig: 'double', shutterMaterial: 'HINGES_ONLY', infillType: 'none' },
      hardware: [{ hardwareType: 'hinge' }, { hardwareType: 'hinge', side: 'back' }],
    }))
    expect(issues).toEqual([])
  })

  it('returns error for a HINGES_ONLY shutter with infill', () => {
    const issues = validateTree(tree({
      regionType: 'shutter',
      paneSpec: { shutterMaterial: 'HINGES_ONLY', infillType: 'glass' },
      hardware: [{ hardwareType: 'hinge' }],
    }))
    expect(issues.some(i => i.message.includes('cannot have infill'))).toBe(true)
  })

  it('returns error for a HINGES_ONLY shutter with beading', () => {
    const issues = validateTree(tree({
      regionType: 'shutter',
      paneSpec: { shutterMaterial: 'HINGES_ONLY', infillType: 'none', hasBeading: true },
      hardware: [{ hardwareType: 'hinge' }],
    }))
    expect(issues.some(i => i.message.includes('cannot have beading'))).toBe(true)
  })

  it('returns split error when a side is below 0.5ft', () => {
    const splitRegion = {
      id: 'sr',
      isLeaf: false,
      width: 1,
      height: 2,
      overlays: [],
      split: {
        direction: 'vertical',
        position: 0.1,  // leaves only 0.1ft on the left
        children: [
          leafRegion({ id: 'c1', width: 0.1, height: 2 }),
          leafRegion({ id: 'c2', width: 0.9, height: 2 }),
        ],
      },
    }
    const issues = validateTree({ frame: { id: 'f', width: 4, height: 3, rootRegion: splitRegion } })
    expect(issues.some(i => i.message.includes('less than 0.5ft'))).toBe(true)
  })
})
