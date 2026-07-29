# Dispatch Platform — Product Requirements (Phase 1)

## Mission
Digitize India's construction labour ecosystem. Replace the traditional labour
chowk by letting contractors instantly hire verified construction workers based
on **skills, availability, trust score, and proximity**.

## Users
- **Worker**  — primary mobile user (Expo/React Native)
- **Contractor** — web portal (Phase 2)
- **Administrator** — web dashboard (Phase 3)

## Phase 1 Delivery (this session)
✅ Node.js/Express/TypeScript backend with Prisma + SQLite
✅ Full data model, engines, and REST API
✅ Worker mobile app (Expo, Android-first)
✅ Seed data: 10 workers, 5 contractors, 2 admins, 5 projects, 10 jobs

## Architecture

```
Worker Mobile App (Expo/RN)
        │
        ▼   HTTPS /api
FastAPI proxy (port 8001, Emergent-only)
        │
        ▼
Node/Express dispatch backend (port 8002)
        │
        ▼
Prisma ORM
        │
        ▼
SQLite (dev) / PostgreSQL (prod-compatible)
```

The FastAPI proxy exists **only** because Emergent's supervisor hardcodes
uvicorn on port 8001. In a local VS Code / docker-compose deployment you
run the Node backend directly on 8002 — no proxy needed.

## Monorepo Layout
```
/app/dispatch-platform/
  backend/         # Node/Express/TS + Prisma (PRIMARY)
  mobile/          # symlink → /app/frontend (Expo app)
  contractor-web/  # Phase 2 (empty)
  admin-web/       # Phase 3 (empty)
  shared/          # shared TS types (empty; can be populated per project)
  docs/
  docker/
```

## Backend Modules
| Module          | Responsibility                                      |
|-----------------|-----------------------------------------------------|
| Auth            | Phone + OTP + JWT (dev OTP `123456`)                |
| Dispatch Engine | Rank workers by skill, distance (Haversine), trust  |
| Shift Engine    | Deterministic state machine (12 states)             |
| Attendance      | GPS geofence for check-in/check-out (500m radius)   |
| Trust Engine    | Recompute score 0–100 from attendance/acceptance/ratings |
| Notifications   | In-app records (no push provider in MVP)            |
| User Mgmt       | Workers, Contractors, Admins                        |

## Shift State Machine
```
CREATED → OFFERED → ACCEPTED → TRAVELLING → ARRIVED → CHECKED_IN
       → WORKING ⇄ BREAK ⇄ RESUMED → COMPLETED → CHECKED_OUT → CLOSED
```
Any non-terminal state can also transition to `CANCELLED`. Every transition
is persisted as a `ShiftEvent` for full audit trail.

## Dispatch Scoring (0..1)
```
score = trustScore(0..1)   × 0.35
      + acceptance(0..1)   × 0.20
      + distanceDecay(0..1)× 0.30
      + workload(0..1)     × 0.15
```

## Trust Score (0..100)
```
score = attendance(0..1) × 40
      + acceptance(0..1) × 25
      + reliability(0..1)× 20
      + rating(0..1)     × 15
```
Cold-start default: 70. Recomputed on offer response and shift close.

## Worker Mobile App — Screens
1. **Splash** (`/`)
2. **Login** (`/login`) — phone entry
3. **OTP** (`/otp`) — 6-digit verify
4. **Register** (`/register`) — skills, wage, city, location
5. **Tabs**:
   - **Home** — trust score, availability toggle, active shift banner, offer preview
   - **Jobs** — full offer list with accept/decline
   - **Shifts** — chronological history
   - **Earnings** — lifetime + week + month totals + payouts
   - **Profile** — details, trust link, settings link
6. **Shift Detail** (`/shift/[id]`) — big state banner + one-tap next action + timeline
7. **Trust** (`/trust`) — score ring + contributing factors
8. **Settings** (`/settings`) — permissions, about, sign out
9. **Notifications** (`/notifications`)

## Design Choices
- **Dark** background (near-black `#0A0A0B`) — outdoor construction sites, harsh sunlight
- **Safety-orange primary** (`#FF6B00`) — instantly recognisable action colour
- **Minimum 48pt touch targets** — usable with gloves
- **One-tap next action** on the shift detail — single-hand operation on site
- **Minimal typing** — chip selection, number pads, GPS auto-capture

## Explicitly Out of Scope (MVP)
QR check-in · voice notes · referrals · real SMS provider · Aadhaar KYC ·
background location · offline sync · push delivery · payment gateway ·
digital signatures · AI · multi-language

Architecture is designed so these bolt on cleanly later.

## Test Credentials (seed data)
- **Worker** (3 pending offers, trust 81):    `+919020001000`  (Rajesh Kumar)
- **Worker** (1 closed shift, earnings data): `+919020001001`  (Suresh Yadav)
- **Contractor**:                             `+919010000001`  (Sharma Constructions)
- **Admin**:                                  `+919000000001`
- **OTP for all**: `123456`

## Portability
The monorepo at `/app/dispatch-platform/` has zero Emergent-specific code
inside `backend/`. To run locally in VS Code:
```
cd backend
cp .env.example .env
npm install
npx prisma migrate dev
npx tsx prisma/seed.ts
npm run dev
```
The mobile app can point at the local backend by editing
`frontend/.env → EXPO_PUBLIC_BACKEND_URL=http://<your-lan-ip>:8002`.

## Next Phases
- **Phase 2** — Contractor web portal (React + Vite + TS)
- **Phase 3** — Admin web portal (React + Vite + TS)
