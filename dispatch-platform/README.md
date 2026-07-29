# Dispatch Platform

A production-grade digital replacement for India's construction labour chowk. Contractors
instantly hire verified workers, ranked by **skill, distance, availability, and trust score**.
Workers accept jobs, track shifts through a strict state machine, and get paid.

**Status:** Phase 1 (Backend + Worker mobile app) shipped.  Phase 2 (Contractor web) and
Phase 3 (Admin web) are scaffolded but empty.

## Monorepo
```
dispatch-platform/
├── backend/          # Node · Express · TypeScript · Prisma · SQLite/PostgreSQL
├── mobile/           # Expo · React Native · TypeScript · Expo Router
├── contractor-web/   # (Phase 2)
├── admin-web/        # (Phase 3)
├── shared/           # cross-project TS types
└── docs/
```

## Quick start (local, no Docker)

### 1. Backend
```bash
cd backend
cp .env.example .env
npm install                 # or: yarn
npx prisma migrate dev
npx tsx prisma/seed.ts
npm run dev                 # http://localhost:8002/api/health
```

### 2. Mobile
```bash
cd mobile                   # (symlink to the Expo project)
# Point the app at your backend (edit .env):
#   EXPO_PUBLIC_BACKEND_URL=http://<your-lan-ip>:8002
yarn install
yarn start                  # scan the QR with Expo Go on Android
```

## Auth (development)
- Phone + OTP flow
- **Dev OTP is `123456`** for every account
- Real SMS provider is out of scope for MVP

## Key API surface
| Method | Path                              | Purpose                                    |
|--------|-----------------------------------|--------------------------------------------|
| POST   | /api/auth/otp/request             | Issue OTP for a phone                      |
| POST   | /api/auth/otp/verify              | Verify OTP → JWT                           |
| GET    | /api/worker/me                    | Current worker profile                     |
| POST   | /api/worker/profile               | Complete/update profile                    |
| GET    | /api/worker/offers                | Pending job offers (dispatch-ranked)       |
| POST   | /api/jobs/offers/accept           | Accept an offer → creates a Shift          |
| GET    | /api/shifts/active                | Current active shift                       |
| POST   | /api/shifts/:id/{action}          | State transitions (travel/arrive/…/close)  |
| GET    | /api/worker/earnings              | Lifetime / week / month totals             |
| GET    | /api/notifications                | In-app notification feed                   |

## Engines
- **DispatchEngine** — Haversine distance + weighted score → JobOffer rows
- **ShiftEngine** — deterministic 12-state machine (see [docs/shift-state-machine.md](docs/shift-state-machine.md))
- **TrustEngine** — 0..100 score from attendance / acceptance / reliability / rating

## Testing
```bash
# Backend typecheck
cd backend && npx tsc --noEmit

# Smoke test (auth → offer → full shift lifecycle → earnings)
# See docs/api-smoke.md
```

## Tech
- Node 20 · Express 4 · TypeScript 5 · Prisma 5 · Zod 3 · JSON Web Tokens
- Expo SDK 54 · React Native 0.81 · Expo Router 6 · Expo Location / SecureStore
- No proprietary APIs — every dependency is standard OSS.
