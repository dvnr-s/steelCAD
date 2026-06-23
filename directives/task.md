# SteelCAD — Implementation Tasks

## Phase 1: Backend Foundation
- [x] Project scaffold (FastAPI + Docker Compose with PostgreSQL)
  - [x] requirements.txt
  - [x] app/config.py + database.py
  - [x] docker-compose.yml + Dockerfile
  - [x] .env configuration
- [x] Database models (SQLAlchemy)
  - [x] User model
  - [x] Design model
  - [x] EstimateVersion model
  - [x] Rate model
- [x] Pydantic schemas
  - [x] User schemas
  - [x] Design tree schemas (recursive)
  - [x] Estimate schemas
  - [x] Rate schemas
- [x] Services
  - [x] Auth service (JWT, password hashing)
  - [x] Pricing engine (pure Python, spec §9)
  - [x] Validation service (invariants + rules)
  - [x] PDF generation service (WeasyPrint)
- [x] API Routers
  - [x] Auth router (register, login, refresh, me)
  - [x] Designs router (CRUD)
  - [x] Estimates router (create, list, get, PDF)
  - [x] Rates router (list, update, seed)
- [x] main.py (FastAPI app assembly)
- [x] Unit tests for pricing engine

## Phase 2: Frontend Canvas
- [x] Vite + React scaffold
- [x] CSS design system (tokens, light/dark, typography)
- [x] Auth pages (login, register)
- [x] Dashboard page (design list, create, delete)
- [x] Editor page shell (Konva stage, sidebar, toolbar)
- [x] Canvas rendering (regions, splits, selection)
- [x] Properties panel (type, paneSpec, grill, hardware)
- [x] API client + live pricing

## Phase 3: Polish & Export
- [x] Estimate view page (full breakdown table)
- [x] PDF export (WeasyPrint template, download)
- [x] Rate management page (admin-only)
- [x] Grill visual overlays (crosshatch MS, bars SS)
- [x] Dimension labels on canvas
- [x] Undo/redo (history in editorStore + toolbar buttons + Ctrl+Z/Ctrl+Shift+Z)
- [x] Validation feedback (live client-side checks in lib/validators.js + panel + blocking toasts)

## Phase 4: Production Readiness
- [x] Docker Compose production config (docker-compose.prod.yml + frontend Dockerfile/nginx)
- [x] CORS + error handling + logging (logging_config.py, request log middleware, global exception handler)
- [x] README + deployment docs
