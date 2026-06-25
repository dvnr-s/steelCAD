# SteelCAD Documentation

This directory is the engineering documentation set for **SteelCAD** — a full-stack
web application for designing and quoting fabricated steel doors and windows.

If you are new to the project, read in this order:

| # | Document | What it covers | Read it when… |
|---|----------|----------------|---------------|
| 1 | [Architecture](./ARCHITECTURE.md) | The whole system end-to-end: components, data flow, request lifecycles, the geometry-tree model, and *how everything actually works*. | You want the complete mental model. **Start here.** |
| 2 | [Domain Model](./DOMAIN_MODEL.md) | The business concepts — designs, frames, regions, panes, grills, hardware — and how the canvas tree encodes them. | You need to understand *what* the app models before *how*. |
| 3 | [Pricing Engine](./PRICING_ENGINE.md) | A deep dive into the deterministic cost engine — the core IP. Frame, splits, panes, grills, hardware, taxes, with worked examples. | You touch pricing, or want to verify a quote. |
| 4 | [Backend Reference](./BACKEND.md) | FastAPI app structure, database schema, every endpoint, services, auth, migrations. | You work on the API or the database. |
| 5 | [Frontend Reference](./FRONTEND.md) | React app structure, routing, state stores, the canvas editor, the API client. | You work on the UI or the editor. |
| 6 | [Development & Operations](./DEVELOPMENT.md) | Local setup, Docker, hot-reload, testing, deployment, and common "how do I…" tasks. | You set up the project or ship it. |

## Authoritative sources

Two documents elsewhere in the repo are **normative** (they define truth; this set
*explains* it):

- [`directives/design_rules_spec.md`](../directives/design_rules_spec.md) — the domain
  specification. Every geometry rule, validation rule, and pricing formula is defined
  there. Code comments reference it by section (`§4A.1`, `R-5`, `INV-7`, `V-18`, …).
  When this documentation and the spec disagree, **the spec wins** — and the docs
  should be corrected.
- [`README.md`](../README.md) — the project's top-level quick-start and feature summary.

## Conventions used in these docs

- **`§N` / `R-N` / `INV-N` / `V-N` / `P-N` / `PR-N`** — references into the design
  rules spec (section, region rule, invariant, validation rule, pane rule, pricing rule).
- **RFT** — running feet (linear feet), the unit for perimeter-based steel pricing.
- File references are clickable relative links, e.g.
  [`backend/app/services/pricing.py`](../backend/app/services/pricing.py).
- ASCII diagrams are used in preference to image binaries so they stay diffable and
  reviewable in version control.
