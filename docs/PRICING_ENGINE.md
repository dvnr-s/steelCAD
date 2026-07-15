# SteelCAD — Pricing Engine

> The pricing engine is the core intellectual property of SteelCAD: it converts a
> geometry tree into an itemized, auditable quotation. This document explains exactly
> how, function by function, with worked examples.
>
> **Source:** [`backend/app/services/pricing.py`](../backend/app/services/pricing.py)
> **Tests:** [`backend/tests/test_pricing.py`](../backend/tests/test_pricing.py)
> **Spec:** [`directives/design_rules_spec.md`](../directives/design_rules_spec.md) §9

---

## 1. Contract & guarantees

```python
price_design(tree: dict, rates: dict,
             discount_type=None, discount_value=0, advance_pct=50) -> dict
```

- **Pure function.** No database, no network, no global state, no randomness. The
  same `(tree, rates, terms)` always yields the same breakdown. This determinism is
  what makes quotations auditable and the engine unit-testable.
- **Input:** the full geometry tree (the same JSON stored in `tree_json`) plus a flat
  `{item_code: rate}` dict.
- **Output:** a structured breakdown — `frame`, `splits[]`, `regions[]`, and the
  rolled-up commercials (`subtotal`, `discount_amount`, `taxable`, `gst`,
  `grand_total`, `advance_amount`).

A second entry point, `price_estimate(frames, rates, …)`, prices a multi-frame
estimate by pricing each frame as a unit, multiplying by quantity, and applying
estimate-level commercial terms once to the aggregate.

---

## 2. The traversal at a glance

`price_design` performs **one depth-first pass** and sums four cost families:

```
 subtotal =  frame steel
          +  Σ split (mullion/transom) steel
          +  Σ per-region (pane + infill + beading + hardware + grill)

 taxable      = subtotal − discount
 gst          = taxable × gst_pct          # default 18%, snapshot per estimate
 grand_total  = round_to_rupee(taxable + gst)
 advance      = round_to_rupee(grand_total × advance_pct / 100)
```

At the **estimate** level, manual *other charges* (PR-9 — labor, transport,
installation) join the frames subtotal before the discount; see §6.

---

## 3. Frame cost

The frame is the outer steel boundary. Its running-feet (RFT) calculation is
**void-aware** and **product-aware** — this is the most nuanced part of the engine.

### Window product — 4-sided, void-aware (`_window_frame_rft`)

A naive window frame would be the full perimeter `2 × (W + H)`. SteelCAD instead sums
**only the outer-edge extent that is backed by an occupied (non-`open`) region**:

```
for each leaf:
    skip if regionType is open/none      # an empty void carries no steel
    if it touches the left  edge → add its height to `left`
    if it touches the top   edge → add its width  to `top`
    if it touches the right edge → add its height to `right`
    if it touches the bottom edge → add its width to `bottom`
        ── EXCEPT a `door` region: a door opens to the floor, so it has no sill
frame_RFT = left + top + right + bottom
```

- For a fully-occupied frame this reduces to the full perimeter `2 × (W + H)`.
- An `open` region reaching an outer edge contributes **no** steel on that edge.
- A `door` leaf touching the bottom contributes **no sill** (it opens to the floor) —
  its jambs/head are unaffected.

### Door product — 3-sided, void-aware (`_door_frame_rft`)

A `productType: "door"` design's base sits in the concrete, so the **entire** bottom
edge is excluded — only left + top + right are summed (still void-aware). For a plain
door this is `2 × H + W`.

### Why the door-sill exemption matters

Without it, the *same composite* (a door with side/top windows) priced as a **window**
would cost more than as a **door**, purely because the window calculation added a sill
beneath the door leaf. The exemption makes them identical — removing a real pricing
ambiguity. The regression test
[`test_window_and_door_frames_match_for_same_layout`](../backend/tests/test_pricing.py)
locks this in.

```
frame_cost = frame_RFT × section_rate          # section_rate = SECTION_{size}_{gauge}
```

---

## 4. Split (mullion / transom) cost

Each `Split` is an interior steel member. Collected recursively by `_collect_splits`:

- **Length** = the parent region's height (vertical split → *mullion*) or width
  (horizontal split → *transom*).
- **Double vs. single section:**
  - **Double** (`2 × section_rate`) when the split divides **two occupied** regions —
    two profiles run back-to-back to partition the unit.
  - **Single** (`1 × section_rate`) when one side is an empty `open` void — it's just a
    single edge member (e.g., the sill/head of a window beside a void).

```
double = all(child subtree contains an occupied leaf  for each side)
rate   = section_rate × 2  if double else section_rate
cost   = length × rate
```

This occupancy rule applies to **all** product types (windows and doors alike) — it's
the `_subtree_has_occupied` helper that decides.

---

## 5. Per-region costs

For each region in the tree, `_walk_regions` accumulates:

### 5.1 Structural pane — `shutter` only (`_compute_pane_structure`)
```
pane_RFT = 2 × (width + height)
cost     = pane_RFT × SHUTTER_{material}        # MS_PIPE=₹100, GP_SHEET=₹250 /RFT
```
`fixed`, `open`, `louver`, and `door` regions have **no** structural pane. (`door`
specifically is priced by the frame, not the leaf — §4A.2.)

A **`HINGES_ONLY`** shutter (§5.8, `shutterMaterial: "HINGES_ONLY"` — customer-supplied,
UI label "No Shutter, only Hinges") also has no structural pane, and no infill or beading:
the customer fabricates the shutter, so `_is_hinges_only` short-circuits
`_compute_pane_structure`/`_compute_jali_pane_structure`/`_compute_infill`/`_compute_beading`
to `None`. Hinges are its only cost. A `HINGES_ONLY` **double** just means we hinge both
faces (front + back) — no second pane. It carries no material rate (nothing in the rate
table).

A **double-shuttered** region (§5.7, `paneSpec.shutterConfig: "double"` — a glass
shutter on one face of the frame, a jali shutter on the other) prices a **second**
full pane run at the jali side's own material rate
(`_compute_jali_pane_structure` → the breakdown's `pane_structure_2` slot):
```
cost₂ = pane_RFT × SHUTTER_{jaliMaterial}
```

### 5.2 Infill — jali only (`_compute_infill`)
```
glass → ₹0 (a label, no line item)
jali  → area = width × height;  cost = area × JALI_WIRE_MESH (₹110/sqft)
```
Jali is **additional** to the structural pane, never a replacement. The jali side of a
double shutter **always** carries this mesh cost (P-15), even though its `infillType`
reads `"glass"` (that field describes the glass side).

### 5.3 Beading — perimeter (`_compute_beading`)
```
requires infill ≠ none (else skipped — V-13)
rf   = beaded_sides × 2 × (width + height)
cost = rf × GLASS_BEADING (₹40/RFT)
```
Applies to **both** glass and jali panes. A single-shuttered region has at most one
beaded side; a double shutter beads each side independently (`hasBeading` = glass side,
`jaliBeading` = jali side) so `beaded_sides` can be 2.

### 5.4 Hardware — per piece (`_compute_hardware`)
```
hinge → quantity × HINGE_{variant}      # SS_12G=₹120, SS_10G=₹260 /pc
lock  → quantity × LOCK_PROVISION       # ₹100 /pc  (door regions only)
```
Back-side hardware on a double-rebate door is labeled "— back side" but priced
identically.

### 5.5 Grill — MS area or SS bar-count (`_compute_grill`)
```
MS_SQUARE      → area = w × h;  cost = area × GRILL_MS_SQUARE (₹100/sqft)
SS_PIPE_*      → bars = max(0, round(2 × height − 2)) + barAdjust   # whole bars, §6.2/§6.2A
                 total_RFT = bars × width
                 cost = total_RFT × GRILL_{material}   # round=₹90, square=₹110 /RFT
```
Grill is read from the region it's attached to (leaf, or branch for SS continuity).
`door` regions never carry grill and are skipped defensively.

SS bar math lives in `services/grill.py` (mirrored 1:1 by `frontend/src/lib/grill.js`),
so pricing, validation (V-20), the canvas and the PDF diagram always agree — the bars
drawn are exactly the bars billed. `barAdjust` is an optional whole-number delta stored
in the overlay's `config` (customer-demanded density, spec §6.2A); when non-zero the
effective count must stay within `1 … floor(height × 6)` or validation rejects it.
The breakdown line carries `bars` / `bar_adjust` fields and notes the adjustment in its
description (e.g. `10 bars (auto 8 +2) × 4ft = 40 RFT × ₹90/RFT`).

---

## 6. Aggregation & commercial terms

```
subtotal = frame_cost + Σ split_costs + Σ region_subtotals      # PR-1/PR-2: 2 dp

# Estimate level only (price_estimate / _apply_commercial_terms):
gross    = subtotal + Σ other_charges.amount                    # PR-9: labor/transport/…

discount:
   PERCENTAGE → gross × value/100
   FLAT       → min(value, gross)
taxable      = gross − discount
gst          = taxable × gst_pct/100                            # PR-4: default 18%
grand_total  = round_to_nearest_rupee(taxable + gst)            # PR-3
advance      = round_to_nearest_rupee(grand_total × advance_pct/100)   # PR-8: default 50%
```

Other charges (`estimates.other_charges`, JSONB `[{label, amount}]`) are manual
line items the geometry cannot derive. They are estimate-level only: never part
of a frame's unit breakdown, the `/price` preview, or the BOM.

Rounding helpers (all `ROUND_HALF_UP`):
- `_round2` — 2 decimal places for all intermediate money.
- `_round_rupee` — nearest whole rupee for the grand total and advance.
- `_fmt_ft` — display formatting for region dimensions (2 dp, trailing zeros dropped).

---

## 7. Rate lookup

Rates are a flat `{item_code: value}` dict, resolved by deterministic codes
(`SECTION_6_18G`, `SHUTTER_MS_PIPE`, `HINGE_SS_12G`, `GRILL_SS_PIPE_ROUND`, …). The
canonical defaults live in `DEFAULT_RATES` in
[`pricing.py`](../backend/app/services/pricing.py) and are seeded into the `rates` table
by `POST /rates/seed`. At request time the live rate table is loaded from the DB, so an
admin's rate edits take effect on the next pricing call — except for already-frozen
estimate snapshots.

| Example code | Rate | Unit |
|---|---|---|
| `SECTION_6_18G` | 175 | per RFT |
| `SHUTTER_MS_PIPE` | 100 | per RFT |
| `GRILL_MS_SQUARE` | 100 | per sqft |
| `GRILL_SS_PIPE_ROUND` | 90 | per RFT |
| `JALI_WIRE_MESH` | 110 | per sqft |
| `HINGE_SS_12G` | 120 | per piece |
| `LOCK_PROVISION` | 100 | per piece |

(Full table in spec §9.2.)

---

## 8. Worked example — a door+window composite

A 6 ft × 9 ft unit (section 6″ 18G → ₹175/RFT), laid out as:

```
┌───────────────┬───────────┐   top strip:  FIXED 6×2   (y=0)
│   FIXED 6×2   │           │   left:       DOOR  3.5×7 (y=2)
├───────────┬───┴───────────┤   top-right:  FIXED 2.5×3 (y=2)
│           │  FIXED 2.5×3  │   bot-right:  OPEN  2.5×4 (y=5, a void)
│ DOOR 3.5×7│───────────────│
│           │  OPEN 2.5×4   │
└───────────┴───────────────┘
```

**Frame (void-aware, 4-sided, door-sill exempt):**
```
left   = FIXED(h=2) + DOOR(h=7)            = 9
top    = FIXED(w=6)                        = 6
right  = FIXED(h=2) + FIXED(h=3)           = 5
bottom = DOOR is sill-exempt → 0           = 0
RFT    = 20  →  20 × 175 = ₹3,500
```

**Splits:** the 2.5 ft transom between the top-right FIXED and the OPEN void borders a
void → **single** section (₹437.50), not double. The other partitions are double.

Priced as a **window** product, this yields exactly the same frame and subtotal as
priced as a **door** product — the door-sill exemption removes the ambiguity. Both come
to **₹12,437.50** (verified by `test_window_and_door_frames_match_for_same_layout`).

---

## 9. How the engine is exercised

- **Live preview** — `POST /price` (`routers/estimates.py::price_preview`) prices a
  tree statelessly for the canvas editor (no persistence).
- **Estimate recompute** — `_recompute` calls `price_design` for every frame on any
  estimate mutation, storing the breakdowns and freezing `rate_snapshot`.
- **Tests** — `test_pricing.py` cross-checks the engine against the spec's worked
  examples (the §13 example, SS-grill bar counts, door composites, the void-aware frame,
  the rebate price-neutrality, discounts/GST/advance). Run them with:
  ```bash
  cd backend && ./venv/Scripts/python -m pytest tests/test_pricing.py
  ```

---

## 10. Invariants the engine relies on (and why it's safe)

The engine assumes the tree is **already valid** (it's gated by
`validate_design_tree` on every write path). It still codes defensively in a few spots
— e.g., skipping grill on `door` regions, treating `regionType in (None, "open")` as a
void — so a slightly malformed tree degrades gracefully rather than mispricing. But the
contract is: **validate first, then price.**
