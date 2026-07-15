/**
 * Client-side design validation — a pragmatic mirror of the backend's
 * validate_design_tree (backend/app/services/validation.py). This gives the
 * user live feedback in the editor before they hit Save, so they aren't
 * surprised by a 422 from the server. The backend remains the source of truth.
 *
 * Returns an array of { id, message } issues. Empty array = valid.
 */
import { dimLabel } from './format'
import { grillBarAdjust, ssGrillAutoBars, ssGrillBarCount, ssGrillMaxBars } from './grill'

// V-20 (§6.2A): manual bar delta is SS-only and, when non-zero, must keep the
// effective count within 1 … floor(height × 6). Mirrors the server rule.
function pushGrillAdjustIssues(region, issues) {
  const label = dimLabel(region)
  for (const overlay of region.overlays || []) {
    const adjust = grillBarAdjust(overlay)
    if (!adjust) continue
    if (!Number.isInteger(adjust)) {
      issues.push({ id: region.id, message: `Grill bar adjustment on ${label} must be a whole number` })
      continue
    }
    if (overlay.material === 'MS_SQUARE') {
      issues.push({ id: region.id, message: `Bar adjustment on ${label} — MS grill has no bar count` })
      continue
    }
    const bars = ssGrillBarCount(region.height, adjust)
    const maxBars = ssGrillMaxBars(region.height)
    if (bars < 1 || bars > maxBars) {
      issues.push({
        id: region.id,
        message: `Grill on ${label} must have 1–${maxBars} bars (auto ${ssGrillAutoBars(region.height)} ${adjust > 0 ? '+' : ''}${adjust} = ${bars})`,
      })
    }
  }
}

function pushLeafIssues(region, issues) {
  const rt = region.regionType
  const ps = region.paneSpec || {}
  const hardware = region.hardware || []
  const label = dimLabel(region)

  // INV-7: every leaf must have a region type
  if (!rt) {
    issues.push({ id: region.id, message: `Region ${label} needs a type` })
    return
  }

  // V-2: minimum region dimensions
  if (region.width < 0.5 || region.height < 0.5) {
    issues.push({ id: region.id, message: `Region ${label} is below the 0.5ft minimum` })
  }

  // V-12: shutter requires a shutter material (door regions have no pane)
  if (rt === 'shutter' && !ps.shutterMaterial) {
    issues.push({ id: region.id, message: `shutter ${label} needs a shutter material` })
  }

  // HINGES_ONLY (§5.8): customer-supplied shutter — we charge hinges only.
  const isHingesOnly = rt === 'shutter' && ps.shutterMaterial === 'HINGES_ONLY'

  // V-19: double shuttering (§5.7) — shutter regions only; a FABRICATED double
  // needs a jali-side material and glass infill. A HINGES_ONLY double (§5.8) is
  // exempt — see V-21.
  const isDoubleShutter = rt === 'shutter' && ps.shutterConfig === 'double'
  if (ps.shutterConfig === 'double') {
    if (rt !== 'shutter') {
      issues.push({ id: region.id, message: `Double shuttering on ${rt} ${label} — only shutter regions can be double-shuttered` })
    } else if (!isHingesOnly) {
      if (!ps.jaliMaterial) {
        issues.push({ id: region.id, message: `Double shutter ${label} needs a jali-side material` })
      }
      if (ps.infillType !== 'glass') {
        issues.push({ id: region.id, message: `Double shutter ${label} must have glass infill (the jali side is implied)` })
      }
    }
  } else if (ps.jaliMaterial || ps.jaliBeading) {
    issues.push({ id: region.id, message: `Jali-side pane fields on ${label} require double shuttering` })
  }

  // V-21: a HINGES_ONLY shutter (§5.8) is customer-supplied — no infill, no
  // beading, no jali-side material
  if (isHingesOnly) {
    if (ps.infillType && ps.infillType !== 'none') {
      issues.push({ id: region.id, message: `Customer-supplied shutter ${label} cannot have infill` })
    }
    if (ps.hasBeading || ps.jaliBeading) {
      issues.push({ id: region.id, message: `Customer-supplied shutter ${label} cannot have beading` })
    }
    if (ps.jaliMaterial) {
      issues.push({ id: region.id, message: `Customer-supplied shutter ${label} cannot have a jali-side material` })
    }
  }

  // V-18: door regions carry hardware only — no pane (material/infill/beading) or grill
  if (rt === 'door') {
    if (ps.shutterMaterial || (ps.infillType && ps.infillType !== 'none') || ps.hasBeading) {
      issues.push({ id: region.id, message: `Door ${label} has no pane (no material, infill, or beading)` })
    }
    if ((region.overlays || []).length > 0) {
      issues.push({ id: region.id, message: `Door ${label} cannot have a grill` })
    }
  }

  // V-5: shutter/door require at least one hinge; a double shutter is hinged
  // per shutter leaf (front = glass side, back = jali side)
  if (rt === 'shutter' || rt === 'door') {
    const hasHinge = hardware.some((hw) => hw.hardwareType === 'hinge')
    if (!hasHinge) {
      issues.push({ id: region.id, message: `${rt} ${label} needs at least one hinge` })
    } else if (isDoubleShutter) {
      const frontHinge = hardware.some((hw) => hw.hardwareType === 'hinge' && hw.side !== 'back')
      const backHinge = hardware.some((hw) => hw.hardwareType === 'hinge' && hw.side === 'back')
      if (!frontHinge || !backHinge) {
        issues.push({ id: region.id, message: `Double shutter ${label} needs a hinge on each side (glass + jali)` })
      }
    }
  }

  // V-14: lock only on door regions
  if (hardware.some((hw) => hw.hardwareType === 'lock') && rt !== 'door') {
    issues.push({ id: region.id, message: `Lock on ${rt} ${label} — locks are door-only` })
  }

  // V-16: back-side hardware requires a double-rebate door or a double shutter
  const hasBack = hardware.some((hw) => hw.side === 'back')
  if (hasBack && !(rt === 'door' && region.rebate === 'double') && !isDoubleShutter) {
    issues.push({ id: region.id, message: `Back-side hardware on ${label} needs a double-rebate door or double shutter` })
  }

  // V-17: doorHand / rebate are meaningful only on door regions
  if (rt !== 'door' && (region.doorHand || (region.rebate && region.rebate !== 'single'))) {
    issues.push({ id: region.id, message: `Door hand/rebate set on a ${rt} region ${label}` })
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

  // V-20: manual bar adjustment bounds (§6.2A)
  pushGrillAdjustIssues(region, issues)
}

function pushBranchIssues(region, issues) {
  const label = dimLabel(region)
  // V-6: branch regions may only carry SS grills, never MS
  for (const overlay of region.overlays || []) {
    if (overlay.material === 'MS_SQUARE') {
      issues.push({ id: region.id, message: `MS grill can't sit on split region ${label}` })
    }
  }
  // V-20: manual bar adjustment bounds (§6.2A) — SS continuity grills too
  pushGrillAdjustIssues(region, issues)
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
