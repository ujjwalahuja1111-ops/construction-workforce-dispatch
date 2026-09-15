# Contractor Web Portal — Phase 2 Spec

**Status:** Not implemented. Scaffolded at `dispatch-platform/contractor-web/`.
This document is the spec another engineer can pick up and build against.

---

## 1. Purpose

Contractors are the **paying side** of the marketplace. The web portal is
where they:

1. Create projects (a construction site).
2. Post labour requests ("jobs") — N workers of skill X on date D.
3. Watch the dispatch fill up in near real-time.
4. Track workers on active shifts, attendance, and pay out.
5. Rate workers at shift close to feed the trust engine.

Every contractor action is already backed by the same data model that the
worker app writes to; the web portal only exposes it from a different
role's perspective.

---

## 2. Tech stack

| Layer     | Choice                                         |
|-----------|------------------------------------------------|
| Bundler   | Vite 5                                         |
| Framework | React 18 + TypeScript                          |
| Routing   | react-router-dom v6 (web only)                 |
| Styling   | CSS modules or Tailwind (team's choice)        |
| Data      | @tanstack/react-query + fetch                  |
| Forms     | react-hook-form + zod (same schemas as backend)|
| Charts    | recharts (small; adequate for MVP)             |

Rationale: same Node/TS ergonomics as the backend, no framework churn,
zod schemas can be shared via the `shared/` folder.

---

## 3. Screens

### 3.1 Login
- Phone + OTP identical to the worker mobile app.
- Rejects if `user.role !== "CONTRACTOR"`.
- Stores JWT in `localStorage` (rotated on every login).

### 3.2 Dashboard (`/`)
KPI header:
- Active projects · Open jobs today · Workers checked in now · Spend this month
- Three charts: dispatch fill rate (last 7 days), attendance %, avg trust score of hired workers.
- Recent-activity feed pulled from a new endpoint `GET /api/contractor/activity`.

### 3.3 Projects (`/projects`)
- Table of all projects (name, city, status, active-jobs count).
- **New project** modal: name, address (geocode via a map picker, e.g. Mapbox/OSM),
  start date, expected end date.
- Row-click → project detail (`/projects/:id`) with jobs & assigned workers.

### 3.4 Labour Requests (`/jobs`)
The core screen. Two tabs: **Open** and **History**.

**New job** modal (already backed by `POST /api/contractor/jobs` when it lands):
- Project (dropdown)
- Skill (chip picker — same 10 codes as the worker app)
- Headcount (int)
- Daily wage (INR)
- Shift date (date picker; today or later)
- Start / end time (24-h)
- Notes (optional)

On submit, the DispatchEngine runs and creates initial offers. The screen
should reflect real-time as offers get accepted/declined (poll every 10 s or
subscribe to the SSE stream when it lands).

### 3.5 Assigned Workers (`/workers`)
- All workers currently on this contractor's shifts (any active state).
- Filter by project / skill / state.
- Row includes worker phone, trust score, current shift state, ETA if `TRAVELLING`.
- Row action: **View profile** (limited view of `Worker` row).

### 3.6 Active Shifts (`/shifts/active`)
Timeline / kanban view:
- Columns = state groups: `Accepted` · `In transit` · `On site` · `Working` · `Break` · `Wrapping up`.
- Cards = shifts. Drag is **not** supported — contractor cannot change worker state directly.
- Click a card → shift detail (`/shifts/:id`) with the full timeline and worker contact.

### 3.7 Attendance (`/attendance`)
- Day picker.
- Table: worker, project, scheduled hours, actual check-in / check-out,
  late/early counters, worked hours, amount.
- Export to CSV (client-side).

### 3.8 Payments (basic) (`/payments`)
Phase-2 has no gateway integration. Show:
- Payable total per closed shift.
- **Mark paid** button → `POST /api/contractor/payments/mark-paid` (new endpoint).
- CSV export.

### 3.9 Worker profile modal
Reused across screens. Shows public fields only: name, skills, exp, city,
trust score breakdown. Contractors can leave a rating **only** for shifts
they own and only after CLOSE.

---

## 4. Backend endpoints to add (Phase 2)

All under `/api/contractor`, all require `role = CONTRACTOR`.

```
GET  /me
POST /profile                        (complete contractor profile)

# Projects
GET  /projects
POST /projects                       ({ name, siteAddress, city, state, latitude, longitude, startsOn, endsOn })
GET  /projects/:id
PATCH /projects/:id                  ({ status } etc.)

# Jobs (labour requests)
GET  /jobs                           (filters: status, projectId, skill, from, to)
POST /jobs                           (already partly implemented in JobService.createAndDispatch)
GET  /jobs/:id
POST /jobs/:id/cancel

# Workers assigned to me
GET  /workers                        (all workers on my shifts)
GET  /workers/:id                    (limited public view)

# Shifts I own
GET  /shifts?state=WORKING
GET  /shifts/:id
POST /shifts/:id/cancel              (contractor cancels)

# Ratings
POST /shifts/:id/rating              ({ score: 1..5, comment? })

# Payments
GET  /payments/pending
POST /payments/:shiftId/mark-paid

# Analytics
GET  /activity                        (recent events feed)
GET  /stats/dashboard                 (KPIs used by /)
```

Every contractor route should include a guard that the resource belongs to
`req.auth.sub`'s contractor (already done for jobs, extend to shifts).

---

## 5. Real-time strategy

Phase 2 can ship with **polling** (10–30 s on active dashboards, 60 s on
historical views). Move to SSE when contractor volumes exceed ~50 concurrent
dashboards. See `Roadmap.md`.

Recommended library: use `EventSource` directly against a
`GET /api/contractor/stream` endpoint that emits typed JSON lines.

---

## 6. Design notes

- **Not a mobile port.** This is a keyboard-driven, dense-table web UI.
- Use a left-nav pattern (Dashboard, Projects, Jobs, Shifts, Attendance, Payments,
  Settings). Dark or light — user's system preference by default.
- Every table needs virtualisation once volumes exceed 500 rows
  (`@tanstack/react-virtual`).
- Every date/time must render in the browser's local timezone but round-trip
  to the server as **UTC ISO strings**.
- No web-only libraries in the mobile app — this portal is free to use any web
  ecosystem package.

---

## 7. Testing strategy

- Vitest for pure functions and reducers.
- Playwright for end-to-end (login → create project → post job → simulated
  worker accepts → shift progresses → rate).
- Reuse the seeded contractor account `+919010000001` (Sharma Constructions).
