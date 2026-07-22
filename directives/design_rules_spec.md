# SteelCAD — Design Rules Spec

> **Status**: Draft v4 — standalone Door product added (productType, 3-sided concrete base, rebate, door hand)
> **Last updated**: 2026-06-23
> **Purpose**: Remove all domain ambiguity BEFORE implementation begins.

This document is the single source of truth for the object model, geometry rules, region semantics, pane model, grill attachment, and pricing derivation. No feature code may be written until this spec is internally consistent and approved.

---

## 1. Core Principle

**The canvas object tree is the source of truth.** Every price, every breakdown line, every validation is derived from explicit geometry objects in the tree — never from form fields, inferred intent, or global toggles.

---

## 2. Object Model

### 2.1 Node Type Taxonomy

Every object in the design is a **node** in a tree. There are exactly six node types:

| Node Type | Role | Structural? | Can Have Children? | Can Have Pane Spec? | Can Have Grill Overlay? | Can Have Hardware? |
|-----------|------|:-----------:|:------------------:|:-------------------:|:-----------------------:|:------------------:|
| `Design` | Root document | — | Yes (1 Frame) | No | No | No |
| `Frame` | Outer boundary | Yes | Yes (1 root Region) | No | No | No |
| `Region` | Bounded area | No | Yes (if branch) / No (if leaf) | Yes (leaf only) | Yes (leaf; SS grill also on branch — see §6) | Yes (leaf only) |
| `Split` | Structural divider | Yes | Yes (exactly 2 child Regions) | No | No | No |
| `Overlay` | Grill layer on region | No | No | — | — | No |
| `Hardware` | Attachment on region | No | No | No | No | — |

### 2.2 Node Properties

Every node carries:

```
id            : uuid         — unique across the design
type          : NodeType     — one of the six types above
parentId      : uuid | null  — null only for Design root
```

#### Design
```
name          : string
description   : string
outerWidth    : number (feet, 2 decimal places)
outerHeight   : number (feet, 2 decimal places)
sectionSize   : "5" | "6" | "10"       — section for frame + all splits
gauge         : "18G" | "16G"          — gauge for frame + all splits
createdAt     : datetime
updatedAt     : datetime
```

#### Frame
```
x             : 0 (always)
y             : 0 (always)
width         : number (= Design.outerWidth)
height        : number (= Design.outerHeight)
sectionSize   : inherited from Design (CANNOT override — same as Design)
gauge         : inherited from Design (CANNOT override — same as Design)
```

#### Region
```
x             : number — position relative to parent
y             : number — position relative to parent
width         : number — computed from parent + split positions
height        : number — computed from parent + split positions
isLeaf        : boolean — true if no child splits
regionType    : RegionType | null — set only when isLeaf=true
paneSpec      : PaneSpec | null — pane specification (see §5); leaf only, for shutter/fixed/door regions
overlays      : Overlay[] — GRILL ONLY; branch regions: SS grill ONLY (see §6)
hardware      : Hardware[] — populated only when isLeaf=true
```

#### Split
```
direction     : "horizontal" | "vertical"
position      : number (0.0–1.0, ratio within parent region)
absolutePos   : number (feet, computed from ratio × parent dimension)
```

> **Frame resize preserves absolute divider position.** When the outer frame is resized,
> each split is held at its absolute divider position (in feet) and its `position` ratio
> is *recomputed* from the new parent size — distinct from a split-drag, which sets the
> ratio directly (see §10.8 vs §10.9).

> **No section/gauge override on splits.** All splits use the same section size and gauge as the Design root. Individual overrides are not supported — this matches actual fabrication practice.

#### Overlay (grill only)
```
overlayType   : "grill"
material      : "MS_SQUARE" | "SS_PIPE_ROUND" | "SS_PIPE_SQUARE"
config        : object — type-specific (e.g., is_continuity for SS grill on branch regions)
```

> **Overlays are exclusively for grill.** Glass, jali, and beading are part of the pane specification (§5), not overlays.

#### Hardware
```
hardwareType  : HardwareType
variant       : string — e.g., "SS_12G", "SS_10G"
quantity      : number — e.g., hinge count
autoComputed  : boolean — true if quantity was auto-derived from dimensions
```

#### PaneSpec
```
shutterConfig   : "single" | "double"             — shutter regions only; default "single".
                                                    "double" = two independent shutter leaves on the
                                                    same opening: a glass shutter on one face of the
                                                    frame and a jali shutter on the other (§5.7)
shutterMaterial : "MS_PIPE" | "GP_SHEET"          — shutter regions only; in a double shutter this
                | "HINGES_ONLY" | null              is the GLASS-side shutter's material.
                                                    "HINGES_ONLY" (customer-supplied shutter, UI
                                                    label "No Shutter, only Hinges") means WE do not
                                                    fabricate the shutter — the customer supplies it;
                                                    we charge hinges only, no pane/infill/beading
                                                    (§5.8, P-17). It applies to the whole region.
infillType      : "none" | "glass" | "jali"      — what fills the pane; a double shutter is always
                                                    "glass" (the jali side is implied — §5.7), EXCEPT
                                                    a HINGES_ONLY shutter which is always "none" (§5.8)
hasBeading      : boolean                         — optional add-on (applicable to glass OR jali);
                                                    in a double shutter: beading on the glass side
jaliMaterial    : "MS_PIPE" | "GP_SHEET" | null  — double shutter only: jali-side shutter's material
                                                    (null when the shutter is HINGES_ONLY — §5.8)
jaliBeading     : boolean                         — double shutter only: beading on the jali side
```

---

## 3. Geometry Tree Structure

### 3.1 Tree Shape

The tree is always:

```
Design
 └── Frame
      └── RootRegion
           ├── [LEAF] → regionType + paneSpec + overlays[] + hardware[]
           └── [BRANCH] → Split
                            ├── ChildRegion (side A)
                            └── ChildRegion (side B)
```

**The tree is binary.** Every split produces exactly two child regions. To create N divisions, the user nests N−1 splits.

Example — 3 horizontal rows:
```
RootRegion [branch]
 └── Split (horizontal, pos=0.33)
      ├── TopRegion [leaf]
      └── BottomTwoThirds [branch]
           └── Split (horizontal, pos=0.50 of remaining)
                ├── MiddleRegion [leaf]
                └── BottomRegion [leaf]
```

### 3.2 Dimension Derivation Rules

Dimensions flow **top-down** from the Design root:

1. `Frame.width = Design.outerWidth`, `Frame.height = Design.outerHeight`
2. `RootRegion.width = Frame.width`, `RootRegion.height = Frame.height`
3. When a Region is split:
   - **Vertical split** at ratio `p`: 
     - ChildA.width = parentRegion.width × p
     - ChildB.width = parentRegion.width × (1 − p)
     - Both children inherit parent height
   - **Horizontal split** at ratio `p`:
     - ChildA.height = parentRegion.height × p
     - ChildB.height = parentRegion.height × (1 − p)
     - Both children inherit parent width
4. Position (x, y) of children is computed from parent position + split offset.

> **Frame resize is position-preserving**: dimension derivation above applies for a fixed
> set of split ratios. When the *frame itself* is resized, each split's ratio is first
> recomputed so the divider keeps its absolute position (§10.8), then dimensions derive
> top-down from the new ratios.

> **Simplification**: Section depth (physical width of mullion/transom material) is NOT deducted from child region dimensions for pricing purposes. This matches current industry practice in the SteelQuote formulas. A future refinement can add deduction if needed.

### 3.3 Invariants

These must always hold:

- **INV-1**: Design has exactly one Frame child.
- **INV-2**: Frame has exactly one root Region child.
- **INV-3**: Every Split has exactly two Region children.
- **INV-4**: A Region is either a leaf (no Split children) or a branch (exactly one Split child).
- **INV-5**: Only leaf Regions may have a regionType, paneSpec, and hardware. Overlays: leaf regions may have grill; branch regions may ONLY have SS grill overlays (see §6.2).
- **INV-6**: A branch Region's regionType is always null; its paneSpec is null; its hardware array is empty. Its overlays array is empty UNLESS it contains an SS grill overlay (continuity model).
- **INV-7**: Every leaf Region MUST have a regionType assigned (default: "open").
- **INV-8**: Split.position is strictly between 0.0 and 1.0 (exclusive).
- **INV-9**: All dimensions are positive and ≥ 0.5 ft (minimum practical region size).
- **INV-10**: All Split nodes inherit sectionSize and gauge from the Design root. No per-split overrides.

---

## 4. Region Types

A leaf region's `regionType` defines what occupies that space:

| RegionType | Meaning | Has Pane Structure? | Has Infill? | Has Hardware? |
|------------|---------|:-------------------:|:-----------:|:-------------:|
| `open` | Empty opening, no infill | No | No | No |
| `fixed` | Fixed (non-operable) panel | No | Optional (glass / jali) | No |
| `shutter` | Operable window pane (hinged); single- or double-shuttered (§5.7) | Yes (RF-based; ×2 panes when double) | Optional (glass / jali; double = glass + jali) | Hinges (window logic, per shutter), **NO lock** |
| `door` | Operable door leaf (hinged) | **No** (leaf not priced separately — §4A.2) | **No** (no infill, no grill) | Hinges (door logic), optional lock |
| `louver` | Ventilation louver | No | No | No |

### 4.1 Region Type Rules

- **R-1**: A region's type is set explicitly by the user. Never inferred.
- **R-2**: Changing a region from branch to leaf (removing splits) resets its type to `open`.
- **R-3**: Subdividing a leaf region (adding a split) clears its type, pane specification, grill overlay, and hardware. The new child leaves default to `open`. **Exception**: SS grill is preserved (see §6.2).
- **R-4**: `shutter` (window pane) hinge auto-computation:
  - height ≤ 6 ft → 2 hinges
  - height ≤ 7 ft → 3 hinges
  - height ≤ 8 ft → 4 hinges
  - height > 8 ft → 5 hinges
- **R-5**: `door` hinge auto-computation:
  - height ≤ 7 ft → 3 hinges
  - height ≤ 8 ft → 4 hinges
  - height > 8 ft → 5 hinges
- **R-6**: The user can override auto-computed hinge count.
- **R-7**: **Lock provision applies ONLY to `door` regions.** Window `shutter` regions NEVER have lock. Do not apply door-style lock costs to window panes.
- **R-8**: Lock is optional on `door` regions. Default: no lock.

---

## 4A. Standalone Door Product

A **Design** has a top-level `productType`:

```
productType : "window" | "door"   — default "window"
```

A `"window"` product behaves exactly as the rest of this spec describes (the outer
frame is a full perimeter, no special base handling). A `"door"` product is a
real steel door unit (a *chowkhat* + leaf, optionally with a fanlight and side
panels). It reuses the **entire region tree** — splits, region types, panes,
infill, grill, hardware — but adds the door-specific rules below.

> A door product is still ONE Design / ONE Frame (assumption §14.22). Its geometry
> tree is identical in shape to a window's; only the rules in this section differ.

### 4A.1 The Base Is In The Concrete (3-Sided Frame)

The outer frame of a door product is set into the floor/concrete on its bottom
edge, so **no steel runs along the base**. The frame is three-sided (two jambs +
head):

```
door_frame_RF      = 2 × frame.height + frame.width      (NOT 2 × (w + h))
door_frame_cost    = door_frame_RF × section_rate
```

This is the only change to frame pricing. Section size, gauge, and the section
rate lookup are unchanged.

### 4A.2 The Door Leaf Has No Pane And Is Not Priced Separately

A `door` region is **not** a window shutter. It has:

- **no structural pane** — no shutter material (MS pipe / GP sheet) and no RF
  pane cost. The door's steel is carried entirely by the chowkhat frame (§4A.1);
  the leaf itself adds **no line item**;
- **no infill** (no glass / jali) and **no beading**;
- **no grill** of any kind.

A `door` region therefore contributes only its **hardware** (hinges, optional
lock — and on a double rebate, the other-side set, §4A.6) plus the cosmetic hand
(§4A.4) and rebate (§4A.5). The chowkhat frame's 3-sided running feet (§4A.1) is
the door's structural cost.

> This corrects the earlier model where a door leaf was priced like a shutter
> pane. Doors do not carry shutter panes, infill, beading, or grill. Finer
> door-leaf details (panel make-up, lock styles) are out of scope for this version
> and will be specified separately.

### 4A.3 Fanlights, Side Panels, and Shared Mullions

- A door product may be subdivided like any window. A **fanlight** (transom above
  the door) or **side panels** (windows flanking the door) are ordinary regions,
  typed and priced by the normal window rules (§5, §6).
- **Side panels need not be full height.** A 5 ft window beside a 7 ft door is
  modelled by splitting the side column horizontally into the window region (top)
  and an `open` region (bottom stub). `open` regions have zero cost (§4), so the
  masonry below the side window is simply not billed.
- The **mullion/transom shared between the door and an adjacent window** is a
  normal `Split` and is priced by the window convention — double section, `length
  × 2 × section_rate` (§9.1 step 2). It is billed once, never per side.

### 4A.4 Door Hand (Left / Right)

A `door` region carries an optional hand label:

```
doorHand : "left" | "right" | null   — default null
```

This is a **labelling / drawing** property only. It has **no pricing effect**. It
indicates the hinge/handle side for fabrication and is drawn on the canvas as a
swing indicator.

### 4A.5 Rebate (Single / Double)

A `door` region carries a rebate:

```
rebate : "single" | "double"   — default "single"
```

- **Rebate does NOT change the frame price.** A single-rebate and a double-rebate
  door frame cost the same (same section, same `2H + W`).
- A **double rebate** door is rebated on both faces, which physically allows a
  second leaf / hardware on the **other (back) side**. Its only effect on the
  model is to *permit* back-side hardware (§4A.6).

### 4A.6 Two-Sided Hardware

Hardware on a `door` region gains an optional side:

```
side : "front" | "back"   — default "front"
```

- `side: "front"` hardware follows the normal door rules (hinges by R-5, optional
  lock, §7).
- `side: "back"` hardware (a second set of hinges and/or a lock for the reverse
  leaf) is **only valid when `rebate: "double"`**. It is priced identically to
  front-side hardware — per piece, summed into the region total. There is no
  separate "back side" rate.

### 4A.7 Deferred (v-next)

- **Jali on the other side** (a mesh leaf on the back of a double-rebate door) is
  intentionally **not** modelled in this version. When added, it will be a
  back-side leaf priced as structural RF + jali mesh area. Until then, the back
  side carries hardware only.

---

## 5. Pane Model — Structural Pane + Infill + Beading

A pane is a **layered object** with three distinct layers that must NEVER be collapsed into one:

```
Pane = Structural Pane Cost + Infill Specification + Optional Beading
```

### 5.1 The Three Pane Layers

| Layer | What it is | Pricing | Applies to |
|-------|-----------|---------|------------|
| **Structural pane** | The physical shutter/pane frame itself | RF-based: `pane_RF × shutter_material_rate` | `shutter` regions only (door regions have NO pane — §4A.2; a `HINGES_ONLY` shutter has none either — §5.8) |
| **Infill** | What fills the pane opening | glass = ₹0; jali = area-based | `shutter` and `fixed` regions |
| **Beading** | Edge trim around the infill | perimeter-based: `pane_perimeter × beading_rate` | Any region with infill (glass OR jali) |

### 5.2 Structural Pane Cost

The pane/shutter structure is priced using running-feet logic, regardless of what infill is inside.

```
pane_RF = 2 × (region.width + region.height)
pane_structure_cost = pane_RF × selected_shutter_material_rate
```

- Applies to `shutter` regions only.
- `fixed` regions do NOT have structural pane cost (they are held directly by the frame/splits).
- `door` regions do NOT have structural pane cost either — the door leaf is not
  priced separately (§4A.2); the chowkhat frame carries the door's steel.
- The shutter material choice (`MS_PIPE` or `GP_SHEET`) is per-region.
- A `HINGES_ONLY` shutter (customer-supplied — §5.8) has NO structural pane cost: the
  customer fabricates the shutter, so we skip the pane RF entirely.

### 5.3 Infill Specification

Infill defines what fills a pane or fixed panel. It is NOT a separate overlay — it is a **specification inside the region**.

| Infill Type | Material Cost | Formula | Notes |
|-------------|:------------:|---------|-------|
| `none` | ₹0 | — | Open pane / no infill |
| `glass` | ₹0 | — | Glass is a label only. No direct material cost in the estimator. |
| `jali` | Area-based | `region.width × region.height × jali_rate_per_sqft` | Jali cost is **additional** to the structural pane cost. Never replaces it. |

### 5.4 Beading

Beading is an optional add-on applied to a region with infill. It is NOT limited to glass.

```
beading_cost = 2 × (region.width + region.height) × beading_rate_per_rft
```

- Can be applied to **glass panes** AND **jali panes**.
- Attached to the specific pane / region — never applied globally.
- Beading only makes sense when the region has an infill (glass or jali). Validation rejects beading on `infillType: "none"`.

### 5.5 Combined Pane Price Formula

For any region with a pane specification:

```
pane_total =
    pane_structure_cost          (shutter regions only; 0 for fixed/door)
  + infill_cost                  (0 for glass, area-based for jali)
  + beading_cost                 (0 if no beading)
```

> `door` regions have NO pane (§4A.2) — they are not in this table. A door
> contributes only hardware; its steel is the chowkhat frame (§4A.1).

**Examples:**

| Region Type | Infill | Beading | Structural | Infill Cost | Beading Cost | Total |
|-------------|--------|---------|:----------:|:-----------:|:------------:|:-----:|
| `shutter` 3×4ft, MS_PIPE | glass | yes | 2×(3+4)×100 = ₹1,400 | ₹0 | 2×(3+4)×40 = ₹560 | ₹1,960 |
| `shutter` 3×4ft, MS_PIPE | jali | yes | ₹1,400 | 3×4×110 = ₹1,320 | ₹560 | ₹3,280 |
| `shutter` 3×4ft, MS_PIPE | jali | no | ₹1,400 | ₹1,320 | ₹0 | ₹2,720 |
| `shutter` 3×4ft, **double** (glass MS_PIPE + jali MS_PIPE), beading glass side only | glass + jali | glass side | ₹1,400 + ₹1,400 | ₹1,320 | ₹560 | ₹4,680 |
| `shutter` 3×4ft, **HINGES_ONLY** (customer-supplied) | none | — | ₹0 | ₹0 | ₹0 | ₹0 (hinges only — §5.8) |
| `fixed` 3×4ft | glass | yes | ₹0 | ₹0 | ₹560 | ₹560 |
| `fixed` 3×4ft | jali | yes | ₹0 | ₹1,320 | ₹560 | ₹1,880 |

### 5.6 Pane Rules

- **P-1**: Pane specification is a property of the region, not a separate node.
- **P-2**: Only leaf regions may have a pane specification.
- **P-3**: `shutter` regions always have structural pane cost (RF-based), regardless of infill.
- **P-4**: `fixed` regions have NO structural pane cost. They can have infill + beading only.
- **P-5**: `open`, `louver`, and `door` regions have NO pane specification. (`door`: see §4A.2 — no pane, infill, beading, or grill.)
- **P-6**: Glass infill has zero material cost. It is a label only.
- **P-7**: Jali infill cost is ADDITIONAL to the structural pane cost. Never replaces it.
- **P-8**: Beading can be applied to BOTH glass and jali panes. It is NOT glass-only.
- **P-9**: Beading requires infill — cannot apply beading to `infillType: "none"`.
- **P-10**: Each region's pane specification is independent. Do not merge or infer across regions.
- **P-11**: When a region is subdivided, its pane specification is cleared.
- **P-12**: `door` regions have NO pane specification at all — no shutter material, no infill, no beading, no grill (§4A.2). Their `paneSpec` is `null`.
- **P-13**: `shutterConfig: "double"` is valid ONLY on `shutter` regions. `fixed`, `door`, `open`, and `louver` regions are always single (§5.7).
- **P-14**: A double shutter is exactly one glass side + one jali side. The glass side is described by `shutterMaterial` / `infillType: "glass"` / `hasBeading`; the jali side by `jaliMaterial` / `jaliBeading`. Each side's structural pane is FULLY priced (`2 × (w + h) × its material rate`) — the second shutter is never free or discounted.
- **P-15**: The jali side of a double shutter always carries the jali mesh cost (area-based; P-7 applies to that side).
- **P-16**: Beading is per side: `hasBeading` beads the glass side, `jaliBeading` beads the jali side. Each beaded side is an independent `2 × (w + h)` run at the beading rate.
- **P-17**: A `HINGES_ONLY` shutter (customer-supplied — §5.8) contributes NO pane structure, NO infill, and NO beading cost — on either side of a double. Its only cost is the hinges we supply (§7). `HINGES_ONLY` overrides every other pane-pricing rule for that region: P-3, P-7, P-8, P-14, P-15, and P-16 do not apply to it.

### 5.7 Double Shuttering (glass + jali)

In fabrication, a window opening can be shuttered on **both faces of the frame**: a glass
shutter on one side and a jali (wire-mesh) shutter on the other — e.g. glass inside for
weather, jali outside for ventilation/insects. This is modeled on a single `shutter` leaf
region via `paneSpec.shutterConfig: "double"`; the region is never split into two leaves
for this.

A double shutter means **two independent shutter leaves on the same opening**:

| Side | Structural pane | Infill | Beading | Hinges |
|------|-----------------|--------|---------|--------|
| Glass side | `2 × (w + h) × rate(shutterMaterial)` | glass = ₹0 | `hasBeading` | `side: "front"` hardware |
| Jali side | `2 × (w + h) × rate(jaliMaterial)` | jali mesh = `w × h × jali_rate` (always) | `jaliBeading` | `side: "back"` hardware |

Rules:

1. Only `shutter` regions may be double-shuttered (P-13). For a **fabricated** double
   (`shutterMaterial` is `MS_PIPE`/`GP_SHEET`), the only supported combination is one
   glass side + one jali side (glass+glass or jali+jali doubles are NOT valid);
   `infillType` stays `"glass"` while double. A **customer-supplied** double
   (`shutterMaterial: "HINGES_ONLY"`) is the exception — both leaves are customer-built,
   so there is no glass/jali material, no infill, and no beading; the "double" only means
   we hinge both faces (§5.8).
2. Both structural panes are fully priced — pane cost is exactly the sum of the two
   sides' RF runs at their own material rates (P-14). The two sides may choose
   different materials (e.g. glass side GP_SHEET, jali side MS_PIPE).
3. Each shutter leaf is hinged independently (HW-9): the glass-side shutter carries
   `side: "front"` hinges, the jali-side shutter `side: "back"` hinges, each auto-counted
   by window logic (R-4) — so a double shutter carries 2× the auto hinge count.
4. Toggling back to single clears `jaliMaterial` / `jaliBeading` and removes all
   `side: "back"` hardware.

**Worked example** — `shutter` 3ft × 4ft, double: glass side MS_PIPE with beading,
jali side MS_PIPE without beading, 2+2 SS_12G hinges:

```
glass-side pane : 2×(3+4) × 100 = ₹1,400
jali-side pane  : 2×(3+4) × 100 = ₹1,400
jali mesh       : 3×4 × 110     = ₹1,320
beading (glass) : 2×(3+4) × 40  = ₹560
hinges          : (2 + 2) × 120 = ₹480
                                  ─────
region subtotal                   ₹5,160
```

### 5.8 Customer-Supplied Shutter (`HINGES_ONLY`)

Sometimes the customer fabricates and installs the shutter leaf (or leaves) themselves,
and we supply **only the hinges**. This is modeled by setting `shutterMaterial` to
`HINGES_ONLY` on a `shutter` region (UI label: **"No Shutter, only Hinges"**).

`HINGES_ONLY` is a fabrication-scope flag on the whole region, not a real material — it
has no material rate. When set:

- **No structural pane cost** — we don't build the shutter frame (overrides P-3).
- **No infill cost** — the customer's shutter carries its own glass/jali; `infillType` is
  forced to `"none"`.
- **No beading cost** — `hasBeading` and `jaliBeading` are forced `false`.
- **Hinges are the only cost** — auto-computed by window logic (R-4 / HW-2) exactly as for
  a fabricated shutter, and priced normally (§7).

**Single vs. double.** `shutterConfig` still applies:

| Config | Meaning | Cost |
|--------|---------|------|
| `single` | Customer supplies one shutter; we hinge one face | front hinges only |
| `double` | Customer supplies shutters on both faces; we hinge both | front + back hinges (HW-9) |

A `HINGES_ONLY` double carries no `jaliMaterial` — both leaves are customer-built, so there
is no per-side material to record. The `"double"` config exists purely to drive the
back-side hinge set (P-17, V-21).

**Worked example** — `shutter` 3ft × 4ft, `HINGES_ONLY`, single, 2 SS_12G hinges (height
4ft ≤ 6ft → 2):

```
structural pane : —          (customer-supplied)
infill          : —
beading         : —
hinges          : 2 × 120 = ₹240
                           ─────
region subtotal              ₹240
```

**Worked example** — same shutter, `HINGES_ONLY`, **double** (customer supplies both faces),
2 + 2 SS_12G hinges:

```
panes / infill / beading : —   (both leaves customer-supplied)
hinges (front + back)    : (2 + 2) × 120 = ₹480
                                           ─────
region subtotal                             ₹480
```

---

## 6. Grill Rules — Definitive

**MS grill and SS grill are two completely different pricing models.** They must never be conflated.

Grill is the **only overlay type** in the system. Glass, jali, and beading are part of the pane specification (§5), not overlays.

These structural rules are absolute:

1. Grill is **NOT** a frame member.
2. Grill is **NOT** a mullion or transom.
3. Grill is **NOT** a global property of the design.
4. Grill **MUST** attach to a specific region selected by the user.
5. If grill is applied to multiple separate regions, **each region is priced independently**.
6. Grill is rendered on the canvas as a **visual pattern overlay** on its attached region.
7. The canvas **MUST** clearly indicate which regions have grill (distinct visual pattern + icon/badge).
8. Default grill scope = the selected region only.
9. Grill is a **layer on top of** the region type and pane spec, not a replacement. A region can be `shutter` + glass infill + grill.
10. The pricing engine reads grill from the **region it is attached to**, never from the design root.
11. Do NOT apply the same calculation logic to MS and SS grill.
12. Do NOT infer grill scope from the overall drawing.
13. Do NOT convert grill into a structural split.

### 6.1 M.S. Grill (Area-Based)

M.S. grill is simple area-based pricing. No bar-count logic.

**Rules:**
- MS grill attaches to a **leaf region only**.
- Cost = `region_width × region_height × MS_grill_rate_per_sqft`.
- No running-feet logic. No bar-count logic.
- If the same design has MS grill on multiple regions, calculate each region separately.
- If a region with MS grill is subdivided, the MS grill is **REMOVED** (per R-3).

| Material | Rate | Formula |
|----------|------|---------|
| M.S. Square | ₹100/sqft | region.width × region.height × 100 |

### 6.2 S.S. Grill (Bar-Count, Continuity Model)

S.S. grill is a repeated-bar pattern. It is **NOT** area-based.

**Bar-count formula:**
```
auto_bars            = max(0, round_half_up((2 × grilled_region_height) − 2))
number_of_grill_bars = auto_bars + bar_adjust        # bar_adjust defaults to 0 (§6.2A)
each bar runs across the grilled_region_width
total_billable_RFT   = number_of_grill_bars × grilled_region_width
SS_grill_cost        = total_billable_RFT × selected_SS_grill_rate_per_RFT
```

Bars are physical objects: the count is always a **whole number** (`round_half_up` =
round to nearest, halves up — identical on client and server). A region too short to
earn a bar (`height ≤ 1 ft` → `auto_bars = 0`) bills zero and **draws zero** — the
canvas must never render decorative bars that are not billed.

**Rendering rule (canvas + PDF diagram):** the billed bars are distributed **evenly
across the grilled region's full height** — `gap = height / (bars + 1)`, bars at
`gap × 1 … gap × bars` — so the pattern always fills the region with equal spacing
and adapts automatically to the bar count (including manual adjustments, §6.2A).
No fixed margins or hardcoded pitch. The number of bars drawn MUST equal the number
of bars billed; a region that bills zero bars draws none.

### 6.2A Manual bar adjustment (`bar_adjust`)

Customers sometimes demand a denser or sparser grill than the house formula. Each SS
grill overlay may carry a whole-number **delta** `bar_adjust` (default `0`) stored in
the overlay's `config`:

- Effective count = `auto_bars + bar_adjust`. The delta is **relative**: resizing the
  region recomputes `auto_bars` and re-applies the delta, so the customer's density
  preference survives geometry changes.
- When `bar_adjust ≠ 0`, the effective count MUST satisfy
  `1 ≤ bars ≤ floor(height × 6)` (at most one bar per 2″ of height). Out-of-range
  states are **rejected by validation (V-20)** — never silently clamped, so the
  billed count always equals what the user sees.
- `bar_adjust` applies to **SS grills only** (MS grill is area-priced — no bar count).
- The adjustment is preserved when switching between SS materials, when the region is
  split (continuity) or merged, and is dropped with the overlay itself.
- The UI must always display the effective count and flag it as adjusted
  (e.g. `15 bars (auto 13, +2)`); customer-facing documents show only the final count.

**Continuity rule:**
- SS grill can attach to **any region — leaf OR branch**.
- When attached to a branch region, the grill visually continues through all internal subdivisions.
- The bar count uses the **full enclosing grilled region's height**, not individual child panel heights.
- The bar width uses the **grilled region's width** (the region the grill is attached to).
- Internal splits do NOT reset the grill count.
- Internal splits do NOT cause separate per-panel grill calculations.
- The grill bars visually pass through mullions/transoms within the grilled region.

**Attachment rules:**
- SS grill can attach to a leaf region (simple case) or a branch region (continuity case).
- When a leaf region with SS grill is subdivided, the SS grill is **PRESERVED** on the now-branch region (it becomes a continuity overlay).
- When the user removes all splits from a branch region with SS grill, the grill remains on the resulting leaf region.

**Separation rule:**
- If SS grill is applied to physically separate regions, calculate each region independently.
- Do NOT merge disconnected grill regions.

| Material | Rate | Formula |
|----------|------|---------|
| S.S. Pipe Round | ₹90/RFT | (round(2 × h − 2) + bar_adjust) × region.width × 90 |
| S.S. Pipe Square | ₹110/RFT | (round(2 × h − 2) + bar_adjust) × region.width × 110 |

**Examples:**

*Example 1: Simple 5ft × 4ft region with SS grill:*
```
bars = (2 × 5) − 2 = 8
billed RFT = 8 × 4 = 32
cost = 32 × SS_grill_rate
```

*Example 2: 6ft × 10ft window, 4ft-wide grilled region with internal splits:*
```
SS grill attached to the 6ft × 4ft region (branch, has internal splits)
bars = (2 × 6) − 2 = 10
billed RFT = 10 × 4 = 40
cost = 40 × SS_grill_rate
(internal splits are irrelevant — grill continues through them)
```

### 6.3 Grill Data Model

The system must explicitly store for each grill overlay:

```
grill_type           : "MS" | "SS"
material             : "MS_SQUARE" | "SS_PIPE_ROUND" | "SS_PIPE_SQUARE"
attached_region_id   : uuid (the region this grill is on)
grilled_region_width : number (feet, from the attached region)
grilled_region_height: number (feet, from the attached region)
is_continuity        : boolean (true if attached to a branch region)
bar_adjust           : integer, default 0 — SS only; manual delta vs. the auto
                       bar count (§6.2A). Stored in the overlay's `config` object.
```

---

## 7. Hardware

Hardware items attach to specific leaf regions.

| HardwareType | Variants | Pricing | Applies To |
|--------------|----------|---------|------------|
| `hinge` | `SS_12G` (₹120/pc), `SS_10G` (₹260/pc) | per piece × quantity | `shutter` and `door` regions |
| `lock` | Standard (₹100/each) | per piece | `door` regions ONLY |

### 7.1 Hardware Rules

- **HW-1**: Hinges are valid on `shutter` (window pane) and `door` regions.
- **HW-2**: `shutter` hinge count: auto-computed using window logic (R-4). ≤6ft → 2, ≤7ft → 3, ≤8ft → 4, >8ft → 5.
- **HW-3**: `door` hinge count: auto-computed using door logic (R-5). ≤7ft → 3, ≤8ft → 4, >8ft → 5.
- **HW-4**: User can override auto-computed hinge count.
- **HW-5**: **Lock provision is ONLY valid on `door` regions.** Never on `shutter` (window pane) regions.
- **HW-6**: Lock is optional on `door` regions, user-toggled. Default: no lock.
- **HW-7**: When a shutter/door region is subdivided, hardware is removed.
- **HW-8**: Default hinge variant: `SS_12G`. User can change.
- **HW-9**: A double-shuttered region (§5.7) is hinged **per shutter**: the glass-side
  shutter's hinges use `side: "front"`, the jali-side shutter's hinges use `side: "back"`.
  Auto-count (HW-2 / R-4) applies to each shutter independently, so a double shutter
  carries twice the auto hinge count. Each side must have at least one hinge (V-5).

---

## 8. Structure vs Pane vs Overlay vs Hardware

This taxonomy prevents confusion:

| Category | Examples | Structural? | Priced by | Scope |
|----------|----------|:-----------:|-----------|-------|
| **Structure (frame)** | Outer frame | Yes | Running feet × section rate | Design-level |
| **Structure (partition)** | Split / Mullion / Transom | Yes | Running feet × section rate × 2 (double section) | Design-level |
| **Region Type** | open, fixed, shutter, door, louver | — | — (defines semantics) | Per leaf region |
| **Pane Structure** | Shutter/door frame (MS pipe, GP sheet) | No | Running feet × shutter rate | Per shutter/door region |
| **Pane Infill** | glass (₹0), jali (area-based) | No | Area or ₹0 | Per region with infill |
| **Pane Beading** | Glass beading | No | Perimeter × beading rate | Per region with infill |
| **Overlay (grill)** | MS square grill, SS pipe grill | No | Area or bar-count RFT | Per region (leaf or branch for SS) |
| **Hardware** | Hinges, locks | No | Per piece | Per leaf region |

**Structure** defines the skeleton and subdivision.
**Region type** defines what a leaf region IS.
**Pane specification** defines the layered pane: structural + infill + beading (§5).
**Grill** is the only overlay — a detachable material layer (§6).
**SS grill** is a special overlay that can span a branch region (continuity model).
**Hardware** are physical attachments ON a leaf region.

---

## 9. Pricing Derivation from Geometry

The pricing engine performs a **full tree traversal** and sums costs from every node:

### 9.1 Traversal Algorithm

```
function priceDesign(tree):
    breakdown = {}
    sectionSize = tree.sectionSize
    gauge = tree.gauge
    sectionRate = lookupRate(sectionSize, gauge)
    
    # 1. Frame cost
    #    Window: full perimeter. Door (§4A.1): 3-sided, base is in the concrete.
    frame = tree.frame
    if tree.productType == "door":
        frameRF = 2 × frame.height + frame.width
    else:
        frameRF = 2 × (frame.width + frame.height)
    breakdown.frame = { rf: frameRF, rate: sectionRate, cost: frameRF × sectionRate }
    
    # 2. Walk all splits → split/mullion/transom cost
    #    Partition members are DOUBLE sections → priced at 2 × sectionRate per RFT.
    mullionRate = sectionRate × 2
    for each split in tree (depth-first):
        splitLength = (split.direction == "vertical") ? parentRegion.height : parentRegion.width
        breakdown.splits.append({ length: splitLength, rate: mullionRate, cost: splitLength × mullionRate })
    
    # 3. Walk ALL regions (depth-first)
    for each region in tree (depth-first):
        regionBreakdown = {}
        
        # 3a. Leaf-only costs: pane spec + hardware
        if region.isLeaf:
            paneSpec = region.paneSpec
            
            # A HINGES_ONLY shutter (§5.8) is customer-supplied: skip pane, infill, and
            # beading entirely — hinges (§3a hardware, below) are its only cost (P-17).
            hingesOnly = region.regionType == "shutter" and paneSpec
                         and paneSpec.shutterMaterial == "HINGES_ONLY"

            # Structural pane cost — shutter regions only.
            # door regions have NO pane (§4A.2); their steel is the chowkhat frame.
            if region.regionType == "shutter" and paneSpec and not hingesOnly:
                paneRF = 2 × (region.width + region.height)
                paneRate = lookupShutterRate(paneSpec.shutterMaterial)
                regionBreakdown.paneStructure = paneRF × paneRate
                # Double shutter (§5.7): the jali-side leaf is a second, fully-priced pane.
                if paneSpec.shutterConfig == "double":
                    regionBreakdown.paneStructure2 = paneRF × lookupShutterRate(paneSpec.jaliMaterial)
            
            # Infill cost — the jali side of a double shutter always carries mesh (§5.7)
            if paneSpec and not hingesOnly and (paneSpec.infillType == "jali" or paneSpec.shutterConfig == "double"):
                regionBreakdown.infill = region.width × region.height × lookupRate("JALI_WIRE_MESH")
            # glass infill = ₹0, no line item needed
            
            # Beading cost — one 2×(w+h) run per beaded side (a double shutter can bead both, P-16)
            beadedSides = 0 if hingesOnly else
                          (1 if paneSpec and paneSpec.hasBeading else 0)
                        + (1 if paneSpec and paneSpec.shutterConfig == "double" and paneSpec.jaliBeading else 0)
            if beadedSides > 0:
                beadingRF = beadedSides × 2 × (region.width + region.height)
                regionBreakdown.beading = beadingRF × lookupRate("GLASS_BEADING")
            
            # Hardware costs
            for each hw in region.hardware:
                hwCost = hw.quantity × lookupHardwareRate(hw.type, hw.variant)
                regionBreakdown.hardware.append(hwCost)
        
        # 3b. Grill overlay costs (leaf OR branch — SS grill can be on branch).
        #     `door` regions never carry grill (§4A.2) — skip them.
        for each overlay in region.overlays where region.regionType != "door":
            if overlay.material == "MS_SQUARE":
                # MS grill: area-based (leaf only, enforced by invariants)
                cost = region.width × region.height × lookupRate("GRILL_MS_SQUARE")
            else:
                # SS grill: bar-count (leaf or branch), whole bars + manual delta (§6.2A)
                bars = max(0, round_half_up((2 × region.height) − 2)) + overlay.bar_adjust
                totalRFT = bars × region.width
                cost = totalRFT × lookupRate(overlay.material)
            regionBreakdown.grill = { type: overlay.material, cost: cost }
        
        breakdown.regions.append(regionBreakdown)
    
    # 4. Aggregate
    subtotal = sum(all costs)
    discount = applyDiscount(subtotal, discountType, discountValue)
    taxable = subtotal - discount
    gst = taxable × 0.18
    grandTotal = round(taxable + gst)  # nearest rupee
    advance = grandTotal × advancePercentage
    
    return { breakdown, subtotal, discount, taxable, gst, grandTotal, advance }
```

### 9.2 Rate Lookup

Rates are resolved from a `RateConfig` table using a deterministic item code:

| Item Code | Rate | Unit |
|-----------|------|------|
| `SECTION_5_18G` | 120 | per RFT |
| `SECTION_5_16G` | 155 | per RFT |
| `SECTION_6_18G` | 175 | per RFT |
| `SECTION_6_16G` | 210 | per RFT |
| `SECTION_10_18G` | 230 | per RFT |
| `SECTION_10_16G` | 270 | per RFT |
| `SHUTTER_MS_PIPE` | 100 | per RFT |
| `SHUTTER_GP_SHEET` | 250 | per RFT |
| _(HINGES_ONLY — no rate; customer-supplied shutter has no pane cost, §5.8)_ | — | — |
| `HINGE_SS_12G` | 120 | per piece |
| `HINGE_SS_10G` | 260 | per piece |
| `GRILL_MS_SQUARE` | 100 | per sqft |
| `GRILL_SS_PIPE_ROUND` | 90 | per RFT |
| `GRILL_SS_PIPE_SQUARE` | 110 | per RFT |
| `GLASS_BEADING` | 40 | per RFT |
| `JALI_WIRE_MESH` | 110 | per sqft |
| `LOCK_PROVISION` | 100 | per piece |
| `BAY_WINDOW_EXTRA` | 40 | per RFT |

### 9.3 Pricing Rules

- **PR-1**: All internal values kept to 2 decimal places.
- **PR-2**: Per-item costs rounded to 2 decimals.
- **PR-3**: Grand total rounded to nearest rupee (integer).
- **PR-4**: GST is applied on the post-discount amount. Default 18%; the percentage
  is configurable in company settings and snapshot onto each estimate at creation.
- **PR-5**: Discount supports `PERCENTAGE` and `FLAT` modes.
- **PR-6**: Rate snapshots are captured with each estimate version.
- **PR-7**: Old estimates NEVER change when rates are updated.
- **PR-8**: Advance percentage defaults to 50%, configurable per estimate.
- **PR-9**: An estimate may carry **other charges** — manual line items
  (`{label, amount}`, amount ≥ 0 in ₹) for costs the geometry cannot derive:
  labor/fabrication, transport, installation, and similar. They are added to the
  frames subtotal **before** discount, so discount and GST apply to the combined
  amount (composite supply). Other charges are estimate-level only — they never
  appear in a frame's unit breakdown or in the bill of materials.

### 9.4 Estimate-Level Aggregation

An estimate prices each frame independently (`unit_subtotal` per §9.1, with no
discount/GST at frame level), multiplies by the frame's `quantity` to get its
`line_total`, then applies commercial terms once to the aggregate:

```
framesSubtotal = Σ line_total                  # all frames
chargesTotal   = Σ charge.amount               # PR-9 other charges
grossSubtotal  = framesSubtotal + chargesTotal
discount       = applyDiscount(grossSubtotal, discountType, discountValue)
taxable        = grossSubtotal − discount
gst            = taxable × gstPct / 100        # PR-4
grandTotal     = round(taxable + gst)          # PR-3: nearest rupee
advance        = round(grandTotal × advancePct / 100)
```

Worked example: frames ₹10,000.00; other charges = Transport ₹1,500 +
Installation ₹2,000 → gross ₹13,500.00; 10% discount → ₹1,350.00;
taxable ₹12,150.00; GST 18% → ₹2,187.00; grand total ₹14,337;
advance 50% → ₹7,169 (rounded from 7,168.50).

---

## 10. What Happens When...

### 10.1 User adds a split to a leaf region
1. Region becomes a branch.
2. Region's type, pane specification, and hardware are **cleared**.
3. Grill overlay: MS grill is **REMOVED**.
4. **Exception**: If the region has SS grill, the SS grill is **PRESERVED** as a continuity overlay on the now-branch region (`is_continuity` becomes true; any `bar_adjust` is carried over).
5. Two new child leaf regions are created with type = `open`.
6. Split is rendered as a line on the canvas.
7. Canvas updates immediately.

### 10.2 User removes a split
1. The split's two child regions are **deleted** (and their subtrees recursively).
2. The parent region becomes a leaf again.
3. Parent region's type resets to `open`.
4. If the branch had SS grill (continuity), it remains on the now-leaf region
   (`is_continuity` becomes false; any `bar_adjust` is carried over). The retained
   grill is removed later only if the user assigns the leaf an `open`/`louver`/`door`
   type (§10.3 step 5).
5. User must re-assign type, pane specification, and other properties.

### 10.3 User changes a region's type
1. The new type is set.
2. If changing TO `shutter`: auto-add hinges (window hinge logic, R-4). Clear paneSpec, user must configure.
3. If changing TO `door`: auto-add hinges (door hinge logic, R-5). paneSpec stays `null` and any grill overlay is removed — a door has no pane or grill (§4A.2). User sets hand / rebate / hardware.
4. If changing FROM `shutter` or `door`: remove hinges and lock hardware. Clear paneSpec.
5. Grill overlay is kept **only when the new type is `fixed` or `shutter`**. Changing
   to `open`, `louver`, or `door` removes the grill overlay (a void or louver carries
   no grill; a door never does, §4A.2). The grill UI offers adding a grill only on
   `fixed`/`shutter` leaves (and branches, SS-only) — but an existing grill on any
   region stays removable.

### 10.4 User sets infill on a region
1. Validate: region is a leaf with type `shutter` or `fixed`. (`door` regions do not have infill — P-12.)
2. User selects infill type: `glass` or `jali`.
3. PaneSpec.infillType is updated.
4. If infill changed from glass/jali to `none`, beading is auto-removed.
5. Pricing updates (jali adds area cost; glass adds ₹0).

### 10.4A User toggles double shuttering on a region
1. Validate: region is a leaf with type `shutter` (P-13).
2. Toggling to `double` on a **fabricated** shutter (`MS_PIPE`/`GP_SHEET`): `infillType` is
   forced to `"glass"` (the jali side is implied); the user selects the jali-side material
   (`jaliMaterial`); a jali-side hinge set is auto-added with `side: "back"` (window hinge
   logic R-4, per HW-9).
   - On a **`HINGES_ONLY`** shutter (§5.8): `infillType` stays `"none"` and no `jaliMaterial`
     is selected — only the `side: "back"` hinge set is auto-added.
3. Toggling to `single`: `jaliMaterial` and `jaliBeading` are cleared; all `side: "back"`
   hardware is removed.
4. Pricing updates (fabricated: second pane run + jali mesh + per-side beading + per-side
   hinges; `HINGES_ONLY`: per-side hinges only).

### 10.4B User selects "No Shutter, only Hinges" (`HINGES_ONLY`) on a shutter (§5.8)
1. Validate: region is a leaf with type `shutter`.
2. `shutterMaterial` is set to `HINGES_ONLY`; `infillType` is forced to `"none"` and
   `hasBeading`, `jaliBeading`, `jaliMaterial` are cleared (V-21). The infill/beading
   editors are hidden.
3. Existing hinges are kept; the shutter still requires at least one hinge (V-5).
4. Pricing updates: pane/infill/beading drop to ₹0; hinges remain the only cost.

### 10.5 User toggles beading on a region
1. Validate: region has infill (glass or jali). Reject if infillType = "none".
2. PaneSpec.hasBeading is toggled.
3. Pricing updates (perimeter-based cost).

### 10.6 User applies MS grill to a region
1. Validate: region is a **leaf**. If branch, reject with message: "M.S. grill can only be applied to a single panel. Select a specific panel."
2. Validate: no existing grill overlay on this region. If exists, replace or reject.
3. An Overlay node (type=grill, material=MS_SQUARE) is created and attached to the region.
4. Canvas renders the crosshatch grill pattern on that region.
5. Pricing updates: area × rate.

### 10.7 User applies SS grill to a region
1. Validate: region is a leaf OR a branch. Both are valid for SS grill.
2. Validate: no existing grill overlay on this region. If exists, replace or reject.
3. User selects SS grill material (SS_PIPE_ROUND or SS_PIPE_SQUARE).
4. An Overlay node (type=grill, material=selected, is_continuity=region.isBranch, bar_adjust=0) is created.
5. Canvas renders the horizontal bar pattern across the entire region (passing through internal splits if branch).
6. Pricing updates: bar-count formula using the attached region's full dimensions.

### 10.7A User adjusts the SS grill bar count (§6.2A)

1. Available only on an SS grill overlay (leaf or branch). MS grill has no bar count.
2. Stepper (−/+) changes `bar_adjust` by ±1; the UI shows the effective count and the
   auto baseline (e.g. `15 bars (auto 13, +2)`) plus the resulting billable RFT.
3. The effective count is kept within `1 … floor(height × 6)`; the stepper clamps
   proactively and validation rejects out-of-range stored states (V-20).
4. "Reset to auto" sets `bar_adjust` back to 0.
5. Pricing and rendering update — drawn bars always equal billed bars.

### 10.8 User resizes the outer frame
1. Frame dimensions update.
2. Each split divider is **held at its absolute position** (feet): its `position` ratio is
   recomputed from the new parent size so the divider does not move. A split on the axis
   *perpendicular* to the changed dimension is unaffected. Ratios are snapped to the grid
   and clamped so each side keeps MIN_SIDE (shrinking the frame past that point pulls the
   divider inward rather than producing an invalid region).
3. All descendant region dimensions **recompute** top-down from the new ratios.
4. All pricing **recomputes** from new geometry (pane costs, infill costs, beading costs, grill costs).
5. SS grill bar counts update based on new region heights (auto count recomputes,
   `bar_adjust` re-applies — §6.2A).
6. Hinge quantities with `autoComputed: true` on `shutter`/`door` leaves recompute
   from the new leaf height (R-4/R-5). User-overridden quantities (`autoComputed:
   false`) are preserved.

### 10.9 User drags a split to reposition it
1. Split.position (ratio) updates.
2. The two child regions resize accordingly.
3. All descendant dimensions recompute.
4. Pricing updates.
5. SS grill costs on any ancestor region update (bar count may change if region height changed; `bar_adjust` re-applies).
6. Auto-computed hinge quantities on affected `shutter`/`door` leaves recompute as in §10.8 step 6.

---

## 11. Validation Rules

The system MUST reject invalid states rather than guessing:

- **V-1**: Frame dimensions must be ≥ 1 ft on each side.
- **V-2**: No region dimension may be < 0.5 ft.
- **V-3**: Split position must leave at least 0.5 ft on each side.
- **V-4**: Every leaf region MUST have a regionType assigned before estimate generation.
- **V-5**: `shutter` and `door` regions MUST have at least one hinge. A double-shuttered
  region (§5.7) must have at least one hinge on EACH side (front and back).
- **V-6**: MS grill cannot be applied to a branch region. SS grill CAN be applied to a branch region.
- **V-7**: The tree must pass all invariants (INV-1 through INV-10) before saving.
- **V-8**: If geometry is ambiguous, reject with a clear error message.
- **V-9**: Grill overlays must have a valid material selected.
- **V-10**: If grill placement is ambiguous, require the user to attach grill to a specific region. Never infer.
- **V-11**: All splits must use the same section size and gauge as the Design root.
- **V-12**: `shutter` regions must have a shutter material selected in paneSpec — `MS_PIPE`, `GP_SHEET`, or `HINGES_ONLY` (customer-supplied — §5.8). (`door` regions have NO pane — see V-18.)
- **V-13**: Beading cannot be applied to a region with `infillType: "none"`.
- **V-14**: Lock cannot be applied to `shutter` (window pane) regions. Only `door` regions.
- **V-16**: `side: "back"` hardware is valid only on a `door` region whose `rebate` is `"double"` (§4A.6) or on a double-shuttered `shutter` region (§5.7, HW-9). A single-rebate door / single shutter has no back side.
- **V-17**: `doorHand` and `rebate` are meaningful only on `door` regions. They are ignored (or rejected) on any other region type.
- **V-18**: `door` regions carry hardware only — they must NOT have a shutter material, infill, beading (paneSpec is `null`), or any grill overlay (§4A.2).
- **V-19**: `shutterConfig: "double"` is valid only on `shutter` regions (P-13). A **fabricated** double shutter (`shutterMaterial` is `MS_PIPE`/`GP_SHEET`) MUST have a jali-side material (`jaliMaterial`) and its `infillType` MUST be `"glass"`. When `shutterConfig` is `"single"` (or absent), `jaliMaterial` and `jaliBeading` must not be set. A `HINGES_ONLY` double is exempt from the jali-material / glass-infill requirement — its constraints are given by V-21.
- **V-20**: `bar_adjust` (§6.2A) must be a whole number and may only be set on SS grill
  overlays. When non-zero, the effective bar count (`auto_bars + bar_adjust`) must be
  ≥ 1 and ≤ `floor(height × 6)` (one bar per 2″ of region height). Out-of-range values
  are rejected — never silently clamped.
- **V-21**: A `HINGES_ONLY` shutter (customer-supplied — §5.8) must have `infillType: "none"`,
  `hasBeading: false`, `jaliBeading: false`, and no `jaliMaterial` — the customer fabricates
  the shutter(s), so we record no pane, infill, or beading. It still must satisfy V-5
  (a `HINGES_ONLY` double needs a hinge on each side, HW-9).
- **V-22**: **Stored geometry must be consistent with the tree that derives it** — the backend
  does not trust frontend-supplied `width`/`height` (§12.2). The root region's `width`/`height`
  must equal the frame's, and each child of a split must have dimensions equal to the parent's
  scaled by the split `position`: a `vertical` split yields child widths `w×position` and
  `w×(1−position)` at the parent's full height; a `horizontal` split yields child heights
  `h×position` and `h×(1−position)` at the parent's full width. Checked within a `0.001` ft
  tolerance (above the frontend's `1e-4` coordinate-cleaning precision). Any inconsistency is
  rejected — this enforces the §12.2 re-derivation contract as a guard against a buggy client
  or a hand-edited tree mispricing.
- **V-23**: `sectionSize` and `gauge` must be present on the design/frame tree — the section
  rate (§9.1) is derived from them. A tree missing either is rejected in validation rather than
  raising during pricing.

---

## 12. Canvas ↔ Backend Contract

### 12.1 Save Flow
1. Frontend serializes the full geometry tree to JSON.
2. POST to backend `/api/designs/`.
3. Backend validates the tree structure (invariants + validation rules).
4. Backend stores the tree JSON in the database.
5. Returns saved design with server-assigned IDs.

### 12.2 Estimate Flow
1. Frontend requests estimate: POST `/api/designs/{id}/estimate/`.
2. Backend loads the tree from DB.
3. Backend re-derives ALL dimensions from the tree (does not trust frontend math). Enforced
   as a validation guard (V-22): the backend rejects any tree whose stored `width`/`height`
   are inconsistent with its frame size and split positions, rather than recomputing them.
4. Backend runs pricing engine with current rate snapshot.
5. Creates EstimateVersion with rate snapshot + full breakdown.
6. Returns detailed breakdown JSON.

### 12.3 Key Contract Rule
**The frontend owns the visual layout and user interaction. The backend owns pricing and validation.** The frontend never computes costs. The backend never renders graphics.

---

## 13. Serialization Format

The geometry tree is serialized as a nested JSON object:

> A `"window"` product omits `productType` or sets it to `"window"`. A door product
> sets `"productType": "door"` and typically has a `door` region carrying `doorHand`
> and `rebate` (and may have `side: "back"` hardware when double-rebate). Example
> door region:
>
> ```json
> {
>   "type": "region", "isLeaf": true, "regionType": "door",
>   "doorHand": "left", "rebate": "double",
>   "paneSpec": null,
>   "overlays": [],
>   "hardware": [
>     { "type": "hardware", "hardwareType": "hinge", "variant": "SS_12G", "quantity": 3, "side": "front" },
>     { "type": "hardware", "hardwareType": "lock",  "variant": "standard", "quantity": 1, "side": "front" },
>     { "type": "hardware", "hardwareType": "hinge", "variant": "SS_12G", "quantity": 3, "side": "back" }
>   ]
> }
> ```
> (A door region has no pane, infill, beading, or grill — only hardware, §4A.2.)

```json
{
  "id": "uuid",
  "type": "design",
  "name": "Kitchen Window",
  "productType": "window",
  "outerWidth": 5.0,
  "outerHeight": 4.0,
  "sectionSize": "5",
  "gauge": "18G",
  "frame": {
    "id": "uuid",
    "type": "frame",
    "width": 5.0,
    "height": 4.0,
    "rootRegion": {
      "id": "uuid",
      "type": "region",
      "x": 0,
      "y": 0,
      "width": 5.0,
      "height": 4.0,
      "isLeaf": false,
      "regionType": null,
      "paneSpec": null,
      "overlays": [],
      "hardware": [],
      "split": {
        "id": "uuid",
        "type": "split",
        "direction": "vertical",
        "position": 0.6,
        "children": [
          {
            "id": "uuid",
            "type": "region",
            "x": 0,
            "y": 0,
            "width": 3.0,
            "height": 4.0,
            "isLeaf": true,
            "regionType": "fixed",
            "paneSpec": {
              "shutterMaterial": null,
              "infillType": "glass",
              "hasBeading": true
            },
            "overlays": [
              {
                "id": "uuid",
                "type": "overlay",
                "overlayType": "grill",
                "material": "MS_SQUARE"
              }
            ],
            "hardware": [],
            "split": null
          },
          {
            "id": "uuid",
            "type": "region",
            "x": 3.0,
            "y": 0,
            "width": 2.0,
            "height": 4.0,
            "isLeaf": true,
            "regionType": "shutter",
            "paneSpec": {
              "shutterMaterial": "MS_PIPE",
              "infillType": "glass",
              "hasBeading": true
            },
            "overlays": [],
            "hardware": [
              {
                "id": "uuid",
                "type": "hardware",
                "hardwareType": "hinge",
                "variant": "SS_12G",
                "quantity": 2,
                "autoComputed": true
              }
            ],
            "split": null
          }
        ]
      }
    }
  }
}
```

This example represents a 5ft × 4ft window with a vertical split at 60%, creating:
- Left panel (3ft × 4ft): fixed, glass infill + beading + M.S. square grill
  - Beading: 2×(3+4)×40 = ₹560
  - MS grill: 3×4×100 = ₹1,200
- Right panel (2ft × 4ft): shutter (MS pipe), glass infill + beading, 2 hinges (height 4ft ≤ 6ft)
  - Pane structure: 2×(2+4)×100 = ₹1,200
  - Beading: 2×(2+4)×40 = ₹480
  - Hinges: 2×120 = ₹240
  - **No lock** (window shutter — lock not applicable)

> **SS grill continuity example**: If the left panel's grill were SS instead of MS, and the user then subdivided the left panel with a horizontal split, the SS grill overlay would remain on the left panel (now a branch region). The bar count would still use the full 4ft height: bars = (2×4)−2 = 6, RFT = 6×3 = 18.

---

## 14. Assumptions

These assumptions are made to remove ambiguity. If any are wrong, update this spec before coding.

1. **v1: All regions are rectangular.** No L-shapes, curves, arches, or polygons in v1. (Note: arched and non-rectangular shapes ARE fabricated — planned for v2.)
2. **Splits go edge-to-edge** within their parent region. No partial splits.
3. **The tree is binary.** Each split creates exactly 2 children. Multi-way splits are represented as nested binary splits.
4. **Section depth is not deducted** from child region dimensions for pricing. (Matches SteelQuote formulas.)
5. **Dimensions are in feet** with 2 decimal places.
6. **Minimum region size: 0.5 ft** on each dimension.
7. **Default new region type: `open`.** User must explicitly set type.
8. **All splits use the same section/gauge as the Design root.** No per-split overrides. This matches actual fabrication.
9. **M.S. grill is area-based.** Cost = region_area × rate/sqft. No bar-count logic.
10. **S.S. grill is bar-count-based.** bars = max(0, round(2 × height − 2)) + bar_adjust (whole bars, §6.2A), RFT = bars × width, cost = RFT × rate. NOT area-based. Drawn bars always equal billed bars.
11. **S.S. grill supports continuity** through internal subdivisions. If the grill visually continues across child regions, use the enclosing region's full height for bar count.
12. **Pane = structural pane + infill + beading.** These three layers are always separate. Never collapsed.
13. **Glass has no material cost.** It is a label / infill state only. No glass-cost line item.
14. **Jali cost is additional to pane structure cost.** Never replaces it.
15. **Beading applies to glass AND jali panes.** Not glass-only.
16. **Window shutters have NO lock provision.** Lock is door-only.
17. **Window shutter hinges:** ≤6ft → 2, ≤7ft → 3, ≤8ft → 4, >8ft → 5.
18. **Door hinges:** ≤7ft → 3, ≤8ft → 4, >8ft → 5.
19. **Shutter material is per-region.** Each shutter region independently chooses MS_PIPE, GP_SHEET, or HINGES_ONLY (customer-supplied — §5.8).
20. **Shutter perimeter** uses the leaf region's own dimensions: `2 × (width + height)`.
21. **v1: Bay window extra** is modeled as a design-level flag/add-on with cost = `totalRF × 40` (where totalRF = frame perimeter + all split lengths). Note: bay window is physically a 3D construct — full 3D bay window modeling is planned for v2+.
22. **One design = one frame.** Multi-frame designs are modeled as separate Design documents.
23. **Hinge count auto-calculation** uses the leaf region's height, not the overall frame height.
24. **Door regions carry hardware only (§4A.2).** A `door` region has no pane (no shutter material), no infill, no beading, and no grill. The door leaf is not priced separately — the chowkhat frame carries its steel.
25. **Door product base is in the concrete (§4A.1).** A `productType: "door"` design's outer FRAME is 3-sided — `2 × height + width` — never billing the bottom run (it sits in the concrete). Window products are unchanged.
26. **Rebate is price-neutral (§4A.5).** Single and double rebate cost the same; double rebate only permits `side: "back"` hardware.
27. **Door hand is cosmetic (§4A.4).** `doorHand` (`left`/`right`) affects drawing only, never price.
28. **Double shuttering (§5.7).** A `shutter` region may carry two independent shutter leaves — glass on one face of the frame, jali on the other. Both structural panes are fully priced at their own material rates, the jali side always carries mesh cost, beading is per side, and each shutter is hinged independently (`front` = glass side, `back` = jali side).
29. **Customer-supplied shutter (§5.8).** A `shutter` region with `shutterMaterial: "HINGES_ONLY"` (UI: "No Shutter, only Hinges") is fabricated by the customer — we charge hinges only, no pane/infill/beading. `single` = one hinged face; `double` = hinges on both faces (no jali material). It overrides all other pane-pricing rules for that region (P-17, V-21).

---

## 15. Glossary

| Term | Definition |
|------|-----------|
| **Design** | The root document representing one complete door/window drawing |
| **Frame** | The outer steel boundary of the design |
| **Split** | A structural divider (mullion if vertical, transom if horizontal) |
| **Mullion** | A vertical split / divider |
| **Transom** | A horizontal split / divider |
| **Region** | A bounded rectangular area within the frame |
| **Leaf region** | A region with no child splits — the terminal node |
| **Branch region** | A region containing a split and two child regions |
| **Region type** | What a leaf region IS (open, fixed, shutter, door, louver) |
| **Pane specification** | The three-layer definition of a region: structural pane + infill + beading |
| **Structural pane** | The physical shutter/door frame, priced by running feet |
| **Double shutter** | Two independent shutter leaves on one opening — a glass shutter on one face of the frame and a jali shutter on the other (§5.7) |
| **Infill** | What fills the pane opening: glass (₹0), jali (area-based), or none |
| **Beading** | Edge trim around infill, priced by perimeter (applies to glass AND jali) |
| **Overlay** | Grill only — a detachable material layer on a region |
| **Continuity overlay** | An SS grill overlay on a branch region, where grill bars span all child regions |
| **Hardware** | A physical attachment on a leaf region (hinge, lock) |
| **Running feet (RFT)** | Linear measurement in feet, used for perimeter-based pricing |
| **Rate snapshot** | A frozen copy of all rates at estimate-generation time |
| **Estimate version** | An immutable snapshot of design + pricing at a point in time |
| **Assembly mode** | How the system handles combination drawings — as a structural graph of regions |
