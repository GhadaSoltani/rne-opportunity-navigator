# Ooredoo Prospect Intelligence — Platform Blueprint

**From "classification pipeline" to "B2B prospect intelligence engine."**
This document is the single source of truth for the merged platform: the product
concept, the intelligence model, the unified data architecture, roles & security,
the technology decision, the professional UI system, the new repository layout, the
API surface, and a phased build plan.

> Scope note. The Python data/ML core you already built (extraction → segmentation →
> analysis → recommendation) is kept **as-is and modular**. We add three new layers on
> top of it — **ingestion/merge**, **scoring/prioritization**, and **auth/RBAC** — and
> replace the presentation layer (Streamlit) with a professional React frontend served
> by the existing FastAPI. Nothing in the ML core has to be rewritten to get there.

---

## 1. Product concept

Ooredoo B2B needs to **find prospects, rank them by value, and spend marketing money
where it pays back**. The platform turns two raw sources — official company records
(RNE) and Google-Maps business listings — into a single, de-duplicated, scored
prospect database that answers four questions for every company:

1. **Who are they?** — sector, size, maturity, location, legal form (from RNE + Maps).
2. **How much are they worth to us?** — a *Value Potential Score* (expected telecom
   revenue opportunity).
3. **How easy are they to win?** — a *Conversion Readiness Score* (reachability +
   digital maturity + freshness + real-world activity).
4. **What do we do about them?** — a *priority tier*, a *recommended marketing channel
   and budget band*, and *recommended offers* from the Ooredoo catalog.

The output is an operational tool, not a report: sales reps get call-ready lists,
managers assign territories and watch conversion, marketing allocates budget to the
segments with the best return, and executives see the market at a glance.

### The core promise, in one line
> *"Given every company in Tunisia we can see, tell me exactly who to call first, who
> to nurture, who to reach cheaply with automation, and who to ignore — and why."*

---

## 2. What changes vs. the version you have

| Area | Today | New platform |
|---|---|---|
| Data sources | RNE PDFs → one CSV | RNE **+** Google Maps, merged into a master entity table |
| Identity of a company | one row per RNE record | one **master prospect**, enriched from both sources |
| Output of the brain | a *category* + confidence | category **+ value score + readiness score + tier + campaign plan + offers** |
| Who uses it | anyone who runs the script | authenticated Ooredoo employees, **role-scoped** |
| UI | Streamlit multipage app | **Next.js (React + TypeScript)** professional app, FastAPI backend |
| Look | dark navy + red glows | **restrained professional design system** (light-first, neutral, one accent) |
| Security | none | **JWT auth, password hashing, RBAC, audit log** |

New modules (each self-contained, following your existing `config.py + logic + main.py`
convention):

- `ingestion/` — load Maps + RNE, resolve them to one entity, write `companies_master.csv`.
- `scoring/` — value model, readiness model, priority tiering, campaign planner.
- `api/auth/` — users, password hashing, JWT, roles, RBAC dependencies, user admin.
- `frontend/` — the Next.js professional UI (replaces `app/`).

---

## 3. The intelligence model (the heart of the platform)

Everything a company row already produces (`analysis/feature_engineering*.py`:
`category`, `capital_tier`, `company_size`, `connectivity_need`, `business_model`,
`multisite_signal`, `is_new_company`, `international_signal`, `digital_signal`,
`dynamism_score`, `eligibility_fibre`, …) plus the Maps enrichment (`phone`, `website`,
`rating`, `reviews_count`, `business_status`) feeds three scores. All scores are
**0–100**, tunable from `scoring/config.py`, and fully explainable (every score keeps a
breakdown of its drivers).

### 3.1 Value Potential Score (VPS) — *how much is this prospect worth?*

A weighted blend of the signals that correlate with telecom spend. Default weights
(sum = 1.0, all in `scoring/config.py`):

| Driver | Weight | Rationale |
|---|---|---|
| Sector telecom propensity | 0.22 | Hotels, banks, clinics spend far more on connectivity than a corner shop |
| Capital tier | 0.20 | Best available proxy for company size/budget |
| Company size class | 0.16 | Employee/scale proxy from legal form + capital |
| Connectivity need | 0.16 | Directly maps to fibre/fixe/data products |
| Multi-site signal | 0.10 | More sites → more lines, SD-WAN, multi-site data |
| B2B business model | 0.08 | B2B firms buy business plans, not consumer SIMs |
| International signal | 0.08 | Roaming, international connectivity, higher ARPU |

Sector propensity is a lookup table (also in config), e.g. tourism 0.90, financial
0.85, healthcare 0.80, transport 0.80, manufacturing 0.75, education 0.65, retail 0.60,
others 0.50. Every band (capital tier, size, connectivity, digital) maps to a 0–1
factor; VPS is the weighted sum × 100.

### 3.2 Conversion Readiness Score (CRS) — *how easily can we win them?*

| Driver | Weight | Rationale |
|---|---|---|
| Reachability (phone/website/email present) | 0.30 | You cannot convert who you cannot contact |
| Digital maturity | 0.20 | Digitally mature firms adopt telecom/IT faster |
| Recency (new company) | 0.18 | New firms are actively setting up services → prime window |
| Maps activity (rating × review volume) | 0.17 | Real, operating, visible business — not a dormant shell |
| Classification confidence | 0.15 | Low-confidence rows are risky to action |

Reachability is the single biggest driver on purpose: a high-value company with no way
to contact them is a marketing problem, not a sales one.

### 3.3 Priority Score & tiers — *what do we do?*

`Priority = 0.60 × VPS + 0.40 × CRS` (tunable). Companies then fall into four
**action tiers** on the value × readiness grid:

```
             READINESS →  low                         high
        ┌───────────────────────────┬───────────────────────────┐
  high  │  B — High-value nurture   │  A — Strategic / invest most │
 VALUE  │  (worth it, but hard to   │  (call first, dedicated AE,  │
   ↑    │   reach → warm up)        │   highest budget)            │
        ├───────────────────────────┼───────────────────────────┤
  low   │  D — Monitor / minimal    │  C — Efficient / low-touch   │
        │  (don't spend; watch)     │  (cheap automated digital,   │
        │                           │   high volume)               │
        └───────────────────────────┴───────────────────────────┘
```

This grid *is* the answer to "who to invest most and least money on":

- **Tier A — Strategic.** Highest expected return **and** reachable now → field sales /
  dedicated account executive, personalized outreach, the biggest per-lead budget.
- **Tier B — High-value nurture.** Big prize but hard to reach → inside sales +
  targeted paid nurture to earn a contact, medium budget.
- **Tier C — Efficient.** Modest value but easy to reach → automated, low-cost digital
  (email/SMS/social), high volume, near-zero human cost. *Best ROI per dinar.*
- **Tier D — Monitor.** Low value, low readiness → **no active spend**; keep in the DB
  and re-score as signals change.

### 3.4 Campaign planner — *channel + budget band*

`scoring/campaign_planner.py` turns tier + reachability into a concrete plan per
company: primary channel (field / tele-sales / email / SMS / social / none), a budget
band (High / Medium / Low / None), and touch cadence. The rule of thumb encoded:
match channel to the cheapest reachable path (phone → tele-sales, website/email →
email nurture, address-only → geo/field or broad digital) and match budget to tier.

### 3.5 Offers

The existing `recommendation/` engine already produces top-N Ooredoo offers per
company. We keep it and surface its output next to the scores, so each prospect card
shows **"worth this much, this easy to win, do this, sell these offers."**

---

## 4. Unified data architecture (the merge)

Two sources describe the same real-world businesses with **no shared key**. `ingestion/`
resolves them.

```
 RNE records ─────────────┐
 (official, legal,        │
  capital, dates,         ├──►  entity_resolution.py  ──►  companies_master.csv
  activity → sector)      │      (fuzzy match on          (one row per real company,
 Google Maps listings ────┘       name + geo + phone)       best fields from both)
 (phone, website, rating,
  reviews, coordinates,
  live status)
```

### 4.1 Matching strategy (`ingestion/entity_resolution.py`)

Blocking + scoring, so we never do an O(n²) full cross-join:

1. **Block** by governorate/city (and first token of the normalized name) to shrink
   candidate pairs.
2. **Score** each candidate pair on: normalized-name similarity (token-set ratio),
   address/locality overlap, and phone-number exact match (a matched phone is nearly
   decisive).
3. **Accept** matches above a high threshold; send borderline pairs to a review file
   (mirrors your existing `review_needed` pattern) rather than guessing.
4. **Merge** with a clear field-precedence policy: RNE wins for legal/official fields
   (capital, dates, legal form, official name); Maps wins for contact/engagement fields
   (phone, website, rating, reviews, coordinates, live status). Unmatched records from
   either side are kept as prospects too — a Maps-only business with no RNE record is
   still a real prospect.

### 4.2 Column resolver (`ingestion/column_resolver.py`)

Your Maps export column names are unknown to me, so ingestion uses a **mapping config**
(same idea as your `analysis/column_resolver.py`): a dict of `canonical_name →
[possible source headers]`. You point it at your real headers once and everything
downstream is stable. Canonical Maps fields the platform expects: `maps_name`,
`maps_address`, `maps_phone`, `maps_website`, `maps_rating`, `maps_reviews_count`,
`maps_category`, `maps_lat`, `maps_lng`, `maps_status`.

### 4.3 Master schema (superset)

`companies_master.csv` = all RNE/analysis columns **+** the Maps enrichment columns **+**
`match_source ∈ {rne_only, maps_only, matched}` and `match_confidence`. This master
becomes the new input to `analysis/` (features) and then `scoring/`.

---

## 5. Roles & permissions

Six roles, least-privilege. Permissions are a matrix in `api/auth/roles.py`, so a route
declares the permission it needs and any role that has it passes.

| Role | Sees | Can do | Cannot do |
|---|---|---|---|
| **Admin** | Everything | Manage users/roles, config, taxonomy, audit log, run pipeline | — |
| **Sales Manager** | Full prospect DB, all territories | Assign leads/territories to reps, dashboards, export | Manage users, edit scoring config |
| **Sales Rep** | **Only assigned prospects** | Update lead status, log calls/notes, see contact info & offers | See unassigned leads, export whole DB, change scores |
| **Marketing Analyst** | Aggregates, segments, all tiers | Build segments, plan/allocate campaign budget, export segment lists | Own/assign individual leads, edit lead status |
| **Data Analyst** | Full data + quality queues | Run pipeline, review classifications, edit taxonomy & validated examples, manage merge review | Manage users, assign leads |
| **Executive / Viewer** | Dashboards & KPIs (read-only) | View, filter, export summaries | Any write action |

Cross-cutting rules: contact details (phone/email) are only exposed to sales/manager/
admin; marketing sees them **aggregated**, not per-lead, to keep the tool clean for
targeting vs. calling. Every write action is written to an **audit log** (who, what,
when) — non-negotiable for an internal enterprise tool.

---

## 6. Security & authentication

Standard, boring, correct — implemented in `api/auth/`:

- **Password hashing:** Argon2 (via `passlib`), never plaintext, never reversible.
- **Auth flow:** OAuth2 password grant → short-lived **JWT access token** (~30 min) +
  longer **refresh token**; tokens signed with an env secret (`JWT_SECRET`).
- **RBAC:** FastAPI dependencies (`require_permission(...)`) guard every route.
  `get_current_user` decodes the token; role → permission set is checked per request.
- **Audit log:** a MongoDB collection (`audit_log`) records every mutating call.
- **Transport & config:** secrets from environment / `.env` (already used for Mongo/
  MinIO), CORS locked to the frontend origin in production, HTTPS terminated at the
  proxy, rate-limiting on `/auth/login`.
- **User lifecycle:** admin creates users and assigns a role; first-login forced
  password reset; deactivation instead of deletion (keeps audit integrity).

This is enough to pass an internal security review without being over-built. If Ooredoo
has an SSO/LDAP provider, the same `get_current_user` seam accepts an OIDC token later
with no changes to the routes.

---

## 7. Technology decision: keep the Python core, replace Streamlit

**Recommendation: migrate the UI to Next.js (React + TypeScript). Keep FastAPI as the
backend. Keep the entire Python ML pipeline untouched.**

Streamlit was perfect for the analytical prototype. It is the wrong tool for what you
just described — a secure, multi-role, professional, data-dense operational tool — for
concrete reasons, not aesthetics:

- **Auth/RBAC:** Streamlit reruns the whole script on every interaction and has no
  first-class session/route/role model. Real per-role views and route guards are a
  fight. FastAPI + a SPA is the standard, clean way.
- **Data-dense UX:** prospect tables with sorting, server-side pagination, saved views,
  inline lead-status edits, virtualized 100k-row grids — this is exactly where React
  data-grids shine and Streamlit strains.
- **Professional look:** the "famous prospection engines" (Apollo, ZoomInfo, Cognism,
  HubSpot) are all React apps with a design system. Matching that polish in Streamlit
  means fighting the framework; in React it's the default path.
- **Separation of concerns / modularity:** a clean API boundary means the same backend
  can later feed other Ooredoo systems — which your `api/routes.py` docstring already
  anticipates.

**Stack:**

- Frontend: **Next.js 14 (App Router) + TypeScript + Tailwind CSS + shadcn/ui**
  (Radix primitives) + **TanStack Table** (grids) + **Recharts** (charts) + **TanStack
  Query** (data fetching). All permissively licensed, all industry-standard.
- Backend: your existing **FastAPI** + the new `api/auth/` and `api/prospects.py`.
- ML/data core: unchanged Python, invoked by FastAPI.
- Data stores: unchanged — MongoDB (metadata, users, audit, lead state), MinIO (PDFs),
  CSV/SQLite artifacts for the analytical outputs (can migrate the master table into
  MongoDB/Postgres later without touching the frontend).

Transition is low-risk: FastAPI stays, the Python pipeline stays, and `app/` (Streamlit)
can live on as an internal admin fallback during the cutover.

> If you strongly prefer to stay Python-only for now, the fallback is FastAPI +
> server-rendered templates (Jinja) + HTMX, which gets you 80% of the polish with no JS
> build step. I still recommend Next.js for the operational tool, but this is a valid
> lighter path and the API layer is identical either way.

---

## 8. Professional design system

Goal: look like an enterprise prospection engine, not a demo. **Light-first, neutral,
one restrained accent.** Ooredoo red is used *sparingly* — for the primary action and a
few key highlights only — never as a background or a glow.

### 8.1 Palette (design tokens)

```
Surfaces
  --bg            #F6F7F9   app background (cool near-white)
  --surface       #FFFFFF   cards, tables, panels
  --surface-2     #F0F2F5   subtle fills, table header
  --sidebar       #0F1B2D   deep slate sidebar (calm, not navy-glow)

Text
  --text          #0B1524   primary
  --text-2        #475467   secondary
  --text-3        #8A94A6   muted / captions

Lines
  --border        #E3E7EC   hairlines, dividers
  --border-strong #CDD3DB

Accent (used sparingly)
  --accent        #E30613   Ooredoo red — primary buttons, active nav, key metric
  --accent-weak   #FDE7E8   accent tints (selected row, badge bg)

Semantic (muted, harmonized — no fluorescent)
  --success       #12876F   --success-bg #E6F4F0
  --warning       #B45309   --warning-bg #FBF0E1
  --danger        #B42318   --danger-bg  #FCE9E7
  --info          #1D6FB8   --info-bg    #E7F0F8

Tier colors (calm, distinct, colorblind-safe-ish)
  Tier A  #1D6FB8 (deep blue)      "Strategic"
  Tier B  #7A5AF8 (muted violet)   "Nurture"
  Tier C  #12876F (teal-green)     "Efficient"
  Tier D  #667085 (slate grey)     "Monitor"

Data-viz sequence (muted, same tonal family)
  #1D6FB8  #12876F  #B45309  #7A5AF8  #C2255C  #0E7490  #667085
```

### 8.2 Typography

- **Inter** (UI) + tabular numbers for all metrics/tables so digits align.
- Scale: 12 / 13 / 14 (body) / 16 / 20 / 24 / 30. Weight 400 body, 500 labels, 600
  headings. Line-height generous (1.5 body). No all-caps except tiny eyebrow labels.

### 8.3 Layout & components

- **Left sidebar** (deep slate), collapsible, role-aware nav. Top bar with global
  search, saved-view switcher, user menu.
- **KPI tiles** — compact, one number + delta + sparkline, thin border, no shadows.
- **Prospect grid** — the centerpiece: dense, sortable, server-paginated, sticky
  header, tier badge chips, value/readiness as small horizontal score bars, row hover,
  bulk-select, column chooser, saved filters.
- **Prospect drawer/detail** — slide-over: identity, scores with explanation, campaign
  plan, recommended offers, contact block (role-gated), activity/notes timeline.
- **Charts** — thin, flat, gridlines faint; no 3D, no glow, no gradients-as-decoration.
- **Elevation** — borders and background contrast, not drop shadows. Radius 8px. Dense
  spacing (8px grid).

The aesthetic north star: Linear/Attio/HubSpot restraint — quiet surfaces, strong
typography, color reserved for meaning (tiers, semantics, one accent).

A **live mockup of the main Prospects screen** in this exact system ships alongside this
guide so you can see and sign off on the direction before we build the full app.

---

## 9. New repository structure

```
ooredoo-prospect-intelligence/
│
├── core/                      # NEW: shared paths, settings, logging (thin)
│
├── extraction/                # unchanged — RNE PDF → rne_companies.csv
├── ingestion/                 # NEW — merge Maps + RNE → companies_master.csv
│   ├── column_resolver.py         flexible header mapping (point at your real columns)
│   ├── maps_loader.py             load + normalize the Google Maps export
│   ├── rne_loader.py              load the RNE/segmented side
│   ├── entity_resolution.py       block → score → match → review
│   └── build_master.py            merge with field-precedence → master table
│
├── segmentation/              # unchanged — sector classification cascade
├── analysis/                  # unchanged — feature engineering (now reads master)
│
├── scoring/                   # NEW — the intelligence layer
│   ├── config.py                  all weights, tables, thresholds, budget bands
│   ├── models.py                  value_potential() + conversion_readiness()
│   ├── priority.py                blend → priority → tier
│   ├── campaign_planner.py        tier + reachability → channel + budget + cadence
│   └── main.py                    orchestrate → prospect_scores.csv
│
├── recommendation/            # unchanged — offer recommendation (Layers 1–4)
│
├── pipeline/                  # runner.py — add ingestion + scoring steps
│
├── api/                       # FastAPI
│   ├── auth/                      # NEW
│   │   ├── security.py            hashing + JWT
│   │   ├── roles.py               roles + permission matrix
│   │   ├── models.py              user schema + Mongo store
│   │   ├── deps.py                get_current_user, require_permission
│   │   └── routes.py              /auth/login, /refresh, /me, user admin
│   ├── prospects.py               # NEW — prospect list/detail/assign/status (RBAC'd)
│   └── routes.py                  existing pipeline/results endpoints
│
├── frontend/                  # NEW — Next.js professional UI (replaces app/)
│   ├── app/                       routes: /login, /prospects, /segments,
│   │                              /campaigns, /company/[id], /admin
│   ├── components/                grid, drawer, kpi-tile, tier-badge, score-bar…
│   ├── lib/                       api client, auth, rbac guard
│   └── styles/                    the design tokens above
│
├── app/                       # legacy Streamlit — keep during cutover, then retire
├── data/
│   ├── input/  (maps export, rne, pdfs)
│   ├── output/ (segmented, features, prospect_scores, recommendations, master)
│   └── knowledge/ (taxonomy, validated_examples, offer_catalog, purchases)
└── PLATFORM_GUIDE.md          # this file
```

---

## 10. API surface (additions)

```
Auth
  POST /auth/login              email + password → access + refresh tokens
  POST /auth/refresh            refresh token → new access token
  GET  /auth/me                 current user + role + permissions
  POST /auth/users              (admin) create user
  PATCH/auth/users/{id}         (admin) change role / deactivate
  GET  /auth/users              (admin) list users

Prospects   (all RBAC-gated; reps auto-scoped to their assignments)
  GET  /prospects               paginated, filterable, sortable master + scores
  GET  /prospects/{id}          full detail: scores+breakdown, plan, offers, contact*
  POST /prospects/{id}/assign   (manager) assign to a rep
  POST /prospects/{id}/status   (rep)     update lead status / log a note
  GET  /segments                (marketing) aggregate segments + budget suggestions
  GET  /prospects/export        role-scoped CSV export

Pipeline / results   (existing, now admin/analyst-gated)
  POST /pipeline/run · /pipeline/segment · /pipeline/llm-audit
  GET  /results/summary · /results/download*
```
`*` contact fields and full-DB export are role-gated per §5.

---

## 11. Pipeline orchestration (new steps)

`pipeline/runner.py` gains two steps, slotted into the existing ordered list so nothing
else changes (exactly the extension pattern your README documents):

```
extraction → ingestion(merge) → rag_build → segmentation → analysis → scoring → recommendation → llm_audit
```

- **ingestion** runs when a Maps export is present; produces `companies_master.csv`,
  which becomes the segmentation/analysis input.
- **scoring** runs after analysis (needs the engineered features); produces
  `prospect_scores.csv`, the table the API/frontend read.

Each is a `_run_*(ctx)` function registered in `PIPELINE_STEPS`, same as today.

---

## 12. Phased build plan

**Phase 0 — Merge & schema (unblocks everything).**
Wire `ingestion/column_resolver.py` to your real Maps headers, run entity resolution,
produce `companies_master.csv`. *Deliverable: one clean master prospect table.*

**Phase 1 — Intelligence.**
Run `scoring/` over the features → `prospect_scores.csv` with VPS, CRS, priority, tier,
campaign plan. Tune weights in `scoring/config.py` against a few known accounts.
*Deliverable: every prospect scored and tiered, explainably.*

**Phase 2 — Secure API.**
Stand up `api/auth/` + `api/prospects.py`, seed an admin user, RBAC every route, audit
log on writes. *Deliverable: a secured backend the frontend can trust.*

**Phase 3 — Professional frontend.**
Build the Next.js app on the design system: login, prospects grid + drawer, segments,
campaigns, admin. Role-aware nav and views. *Deliverable: the operational tool.*

**Phase 4 — Operate & learn.**
Feed real outcomes (calls, wins) back as a signal; re-score on a schedule; add the
collaborative layer's purchase history to sharpen VPS. Retire Streamlit.

---

## 13. What I need from you to finish Phase 0–1 precisely

The new code is written to be schema-flexible, but to lock the merge and scoring to your
*actual* data I need:

1. **The Google Maps export** (a sample is fine) — so I can fill in the real header names
   in `ingestion/column_resolver.py` and confirm which enrichment signals exist
   (phone? website? email? rating? reviews? coordinates?).
2. **`data/output/company_features.csv`** (or a run of `analysis/`) — so I can verify the
   exact feature column names/values the scoring engine reads (`company_size`,
   `connectivity_need`, `business_model`, `digital_signal` levels, etc.).
3. **Confirmation of the offer catalog & any purchase history** you want the campaign
   plan and VPS to lean on (`offer_catalog.csv` is already here; `purchases.xls` too).

Drop those in and I'll pin every mapping, tune the default weights to your data, and we
move straight into Phase 2 (auth) and Phase 3 (the frontend).
