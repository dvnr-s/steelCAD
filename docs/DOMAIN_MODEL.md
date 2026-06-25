# SteelCAD — Domain Model

> This document explains **what the application models** — the business concepts and
> how they are encoded in the geometry tree — in plain language. It distills the
> normative [`directives/design_rules_spec.md`](../directives/design_rules_spec.md) for
> a newcomer. When in doubt, the spec is authoritative.

---

## 1. The mental model

A fabricator builds a steel **door** or **window** as an outer frame subdivided by
steel bars (mullions/transoms) into rectangular panels. Each panel is filled with
something — glass, a hinged shutter, a mesh, a door leaf, or left open — and may carry a
decorative grill and hardware (hinges, locks).

SteelCAD represents exactly that, as a tree of typed objects.

```
Design  ─ the whole drawing (a window OR a door product)
  └ Frame  ─ the outer steel boundary
      └ Region  ─ a rectangular area; either split further, or a terminal "leaf"
          ├ Split  ─ the steel bar dividing a region in two (mullion/transom)
          ├ PaneSpec  ─ what fills a leaf (shutter material + infill + beading)
          ├ Overlay  ─ a grill layered on a region
          └ Hardware  ─ hinges / locks attached to a leaf
```

---

## 2. The six node types

Every object is a node. There are exactly six types (spec §2.1):

| Node | Role | Children | Pane? | Grill? | Hardware? |
|------|------|----------|:-----:|:------:|:---------:|
| **Design** | Root document | 1 Frame | – | – | – |
| **Frame** | Outer boundary | 1 root Region | – | – | – |
| **Region** | Bounded area | a Split (branch) **or** none (leaf) | leaf only | leaf; SS-grill also on branch | leaf only |
| **Split** | Structural divider | exactly 2 Regions | – | – | – |
| **Overlay** | Grill layer | none | – | – | – |
| **Hardware** | Attachment | none | – | – | – |

### Design-level properties

`productType: "window" | "door"`, `outerWidth`, `outerHeight`, `sectionSize`
(`"5"|"6"|"10"` inches), `gauge` (`"18G"|"16G"`). The section and gauge apply to the
frame **and every split** — there are no per-split overrides (matches fabrication
practice, INV-10).

---

## 3. Regions: the workhorse

A **Region** is either:

- a **branch** — it owns a `Split`, which owns two child regions. A branch has
  `regionType: null`, no pane, no hardware (and no overlays except an SS-grill
  continuity overlay).
- a **leaf** — a terminal panel with a `regionType` and, depending on that type, a
  pane, grills, and hardware.

### Region types (leaf only)

| Type | Meaning | Pane structure | Infill | Hardware |
|------|---------|:--------------:|:------:|---------|
| `open` | Empty opening / void | No | No | No |
| `fixed` | Fixed (non-operable) panel | No | glass / jali | No |
| `shutter` | Operable window pane (hinged) | **Yes** (RFT-based) | glass / jali | Hinges (window logic), **no lock** |
| `door` | Operable door leaf | **No** (not priced separately) | **No** | Hinges (door logic), optional lock |
| `louver` | Ventilation louver | No | No | No |

Two subtleties that trip people up:

- **`open` regions are free.** They carry no steel and no cost. They model deliberate
  voids — e.g., the masonry gap below a half-height side window next to a door. The
  canvas draws them with a diagonal hatch.
- **`door` regions carry hardware only.** A door leaf has *no* pane, infill, beading,
  or grill. Its steel is accounted for by the frame (the *chowkhat*), not the leaf
  (spec §4A.2). This is different from a `shutter`, which *does* have a priced pane.

### Hinge auto-counts

Set automatically from the leaf's **height** when you assign the type (overridable):

- **Shutter** (window): ≤6ft → 2, ≤7ft → 3, ≤8ft → 4, >8ft → 5 (R-4).
- **Door**: ≤7ft → 3, ≤8ft → 4, >8ft → 5 (R-5).

---

## 4. The pane model: three independent layers

A pane is **never** a single thing. It is three separable layers (spec §5):

```
Pane = Structural pane  +  Infill  +  Beading
       (the shutter      (what fills   (edge trim
        frame itself)     the opening)  around infill)
```

| Layer | What | Priced by | Applies to |
|-------|------|-----------|------------|
| **Structural pane** | The physical shutter frame (MS pipe / GP sheet) | `2×(w+h) × material_rate` (RFT) | `shutter` only |
| **Infill** | What fills the opening | glass = ₹0 (a label); jali = `w×h × jali_rate` (area) | `shutter`, `fixed` |
| **Beading** | Edge trim around infill | `2×(w+h) × beading_rate` (perimeter) | any region with infill |

Rules worth memorizing:

- `fixed` panels have **no** structural pane cost — the frame/splits hold the glass
  directly (P-4).
- Glass is **free** — a label, not a cost line (P-6).
- Jali is **additional** to the structural pane, never a replacement (P-7).
- Beading needs infill — you can't bead an empty pane (P-9, V-13).
- `door` regions have **no pane at all** (`paneSpec: null`) (P-12, V-18).

---

## 5. Grills: two completely different models

Grill is the **only** overlay type. It attaches to a *specific region* — never globally
inferred (spec §6). MS and SS grills use **different** pricing models and must never be
conflated:

| Grill | Attaches to | Formula |
|-------|-------------|---------|
| **MS square** | leaf only | `width × height × rate` (area) |
| **SS pipe (round/square)** | leaf **or branch** | `((2×height) − 2) × width × rate` (bar-count) |

The SS grill's **continuity model** is the interesting one: when applied to a *branch*
region, the bars visually run straight through the internal mullions/transoms, and the
bar count uses the **enclosing region's full height** — not the child panels'. That's
why an SS grill is *preserved* (becomes a continuity overlay) when you subdivide a leaf
that has one, whereas an MS grill is removed (spec §6.2, R-3).

---

## 6. Hardware

Attaches to leaf regions (spec §7):

| Hardware | Variants | Priced | Valid on |
|----------|----------|--------|----------|
| **Hinge** | `SS_12G` (₹120/pc), `SS_10G` (₹260/pc) | per piece × qty | `shutter`, `door` |
| **Lock** | standard (₹100) | per piece | **`door` only** |

A **double-rebate door** may carry a second set of hardware on the *back* side
(`side: "back"`), priced identically to the front. A single-rebate door has no back
side (V-16).

---

## 7. The standalone Door product

Setting `productType: "door"` turns the design into a real steel door unit (a chowkhat +
leaf, optionally with a fanlight and side panels). It reuses the **entire** region tree;
only these rules change (spec §4A):

- **3-sided frame (§4A.1).** The base sits in the concrete, so no steel runs along the
  bottom: `frame ≈ 2×height + width` instead of the full perimeter.
- **Door region = hardware only (§4A.2).** No pane, infill, beading, or grill.
- **Door hand (§4A.4).** `left`/`right` — a drawing label, **no price effect**. Drawn as
  the swing triangle on the canvas.
- **Rebate (§4A.5).** `single`/`double` — **price-neutral**; double rebate only *permits*
  back-side hardware.
- **Composites (§4A.3).** Fanlights and side windows are ordinary regions priced by the
  normal window rules; the shared mullion between door and window is billed once.

> SteelCAD also applies a *void-aware* refinement: even inside a **window** product, a
> `door` region carries **no bottom sill** (a door opens to the floor). This makes the
> same composite price identically whether modeled as a window or a door product. See
> [Pricing Engine](./PRICING_ENGINE.md#frame).

---

## 8. Lifecycle: what happens when…

A few key transitions (spec §10) — these are implemented in
[`editorStore.js`](../frontend/src/store/editorStore.js):

- **Add a split to a leaf** → it becomes a branch; its type, pane, hardware, and MS
  grill are cleared; two new `open` child leaves appear. *Exception:* an SS grill is
  preserved as a continuity overlay.
- **Remove a split** → children are deleted; the parent becomes a leaf and resets to
  `open`.
- **Change region type** → switching *to* `shutter`/`door` auto-seeds hinges; switching
  *to* `door` also drops any pane and grill; switching *away* removes hinges/lock.
- **Resize the frame / drag a mullion** → all descendant dimensions recompute
  (`relayout`), and prices (including SS-grill bar counts that depend on height)
  recompute.

---

## 9. Invariants & validation (the guardrails)

The tree must always satisfy structural **invariants** (INV-1…INV-10) and **validation
rules** (V-1…V-18). A few of the most load-bearing:

- **INV-3/INV-4** — every split has exactly two children; a region is leaf XOR branch.
- **INV-7** — every leaf has a `regionType` (default `open`).
- **V-2/V-3** — no region under 0.5 ft; a split must leave ≥0.5 ft each side.
- **V-5** — `shutter`/`door` must have ≥1 hinge.
- **V-12** — `shutter` must have a shutter material.
- **V-14** — a lock is valid only on `door`.
- **V-18** — `door` carries hardware only (no pane, no grill).

These are enforced authoritatively by
[`services/validation.py`](../backend/app/services/validation.py) and mirrored for live
feedback by [`lib/validators.js`](../frontend/src/lib/validators.js).

---

## 10. Glossary

| Term | Meaning |
|------|---------|
| **Mullion** | A vertical split / divider |
| **Transom** | A horizontal split / divider |
| **Chowkhat** | The outer door frame |
| **Leaf / branch region** | A terminal panel / a region that's been subdivided |
| **Pane spec** | The three-layer fill of a leaf: structural + infill + beading |
| **Infill** | What fills a pane: glass (₹0), jali (area-priced), or none |
| **Beading** | Edge trim around infill, priced by perimeter |
| **Overlay** | A grill — the only overlay type |
| **Continuity overlay** | An SS grill on a branch, spanning child regions |
| **RFT** | Running feet (linear feet) — the unit for perimeter steel |
| **Rebate** | Single/double — double permits back-side door hardware |
| **Void** | An `open` region — zero cost, no steel |

> Continue to [Pricing Engine](./PRICING_ENGINE.md) to see how these concepts turn into
> rupees.
