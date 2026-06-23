/**
 * Client-side design validation — a pragmatic mirror of the backend's
 * validate_design_tree (backend/app/services/validation.py). This gives the
 * user live feedback in the editor before they hit Save, so they aren't
 * surprised by a 422 from the server. The backend remains the source of truth.
 *
 * Returns an array of { id, message } issues. Empty array = valid.
 */

function pushLeafIssues(region, issues) {
  const rt = region.regionType
  const ps = region.paneSpec || {}
  const hardware = region.hardware || []
  const label = `${region.width}×${region.height}`

  // INV-7: every leaf must have a region type
  if (!rt) {
    issues.push({ id: region.id, message: `Region ${label} needs a type` })
    return
  }

  // V-2: minimum region dimensions
  if (region.width < 0.5 || region.height < 0.5) {
    issues.push({ id: region.id, message: `Region ${label} is below the 0.5ft minimum` })
  }

  // V-12: shutter/door require a shutter material
  if ((rt === 'shutter' || rt === 'door') && !ps.shutterMaterial) {
    issues.push({ id: region.id, message: `${rt} ${label} needs a shutter material` })
  }

  // V-5: shutter/door require at least one hinge
  if (rt === 'shutter' || rt === 'door') {
    const hasHinge = hardware.some((hw) => hw.hardwareType === 'hinge')
    if (!hasHinge) {
      issues.push({ id: region.id, message: `${rt} ${label} needs at least one hinge` })
    }
  }

  // V-14: lock only on door regions
  if (hardware.some((hw) => hw.hardwareType === 'lock') && rt !== 'door') {
    issues.push({ id: region.id, message: `Lock on ${rt} ${label} — locks are door-only` })
  }

  // V-15: door regions must be solid (infill "none")
  if (rt === 'door' && ps.infillType && ps.infillType !== 'none') {
    issues.push({ id: region.id, message: `Door ${label} must be a solid panel (no infill)` })
  }

  // V-13: beading requires infill
  if (ps.hasBeading && (!ps.infillType || ps.infillType === 'none')) {
    issues.push({ id: region.id, message: `Beading on ${label} requires glass or jali infill` })
  }

  // V-9: grill overlays must have a material
  for (const overlay of region.overlays || []) {
    if (!overlay.material) {
      issues.push({ id: region.id, message: `Grill on ${label} needs a material` })
    }
  }
}

function pushBranchIssues(region, issues) {
  const label = `${region.width}×${region.height}`
  // V-6: branch regions may only carry SS grills, never MS
  for (const overlay of region.overlays || []) {
    if (overlay.material === 'MS_SQUARE') {
      issues.push({ id: region.id, message: `MS grill can't sit on split region ${label}` })
    }
  }
}

function walk(region, issues) {
  if (region.isLeaf) {
    pushLeafIssues(region, issues)
    return
  }
  pushBranchIssues(region, issues)
  if (region.split) {
    // V-3: each side of a split must keep at least 0.5ft
    const { direction, position } = region.split
    const sideA = direction === 'vertical' ? region.width * position : region.height * position
    const sideB = direction === 'vertical' ? region.width * (1 - position) : region.height * (1 - position)
    if (sideA < 0.5 || sideB < 0.5) {
      issues.push({ id: region.id, message: `A split leaves less than 0.5ft on one side` })
    }
    for (const child of region.split.children) walk(child, issues)
  }
}

/**
 * Validate a design tree (client store shape). Returns an array of issues.
 */
export function validateTree(tree) {
  const issues = []
  if (!tree?.frame?.rootRegion) {
    return [{ id: null, message: 'Design has no frame' }]
  }
  if (tree.frame.width < 1 || tree.frame.height < 1) {
    issues.push({ id: tree.frame.id, message: 'Frame must be at least 1ft on each side' })
  }
  walk(tree.frame.rootRegion, issues)
  return issues
}
