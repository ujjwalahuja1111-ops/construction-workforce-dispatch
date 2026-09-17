# Construction Workforce Dispatch Platform

A backend + worker mobile app for dispatching construction labour: contractors
post jobs, workers are ranked and offered work by skill/distance/trust score,
and a worker mobile app carries them through OTP login, offer accept/decline,
and a GPS-geofenced shift lifecycle (travel → arrive → check-in → work →
check-out → close) through to earnings.

**Current scope (Phase 1 / MVP):** the backend API and the worker mobile app
are implemented. **There is no contractor or admin web application yet** —
`dispatch-platform/contractor-web/` and `dispatch-platform/admin-web/` do not
exist in this repository; only their names appear in planning docs. Jobs and
projects currently enter the system only via the database seed script, not
through an exposed API endpoint — see `dispatch-platform/docs/KnownLimitations.md`
§6 for the details.

## Where things actually are

| What | Where | Stack |
|---|---|---|
| **Backend API** (the real one) | [`dispatch-platform/backend/`](dispatch-platform/backend/) | Node 20 · Express 4 · TypeScript 5 · Prisma 5 · SQLite (dev) |
| **Worker mobile app** (the real one) | [`frontend/`](frontend/) | Expo SDK 54 · React Native 0.81 · Expo Router 6 |

`dispatch-platform/mobile` is a symlink to `frontend/` that only resolves
inside the original Emergent development environment — it is not needed and
will appear broken on a normal checkout; use `frontend/` directly.

The root `backend/` directory (Python/FastAPI) is **not** the application
backend — it's a thin reverse-proxy shim that exists only to satisfy the
original Emergent sandbox's supervisor. You do not need it for local
development; run the Node backend in `dispatch-platform/backend/` directly.
It, along with `.emergent/`, `test_result.md`, and `test_reports/`, is legacy
tooling scaffolding kept for now and slated for a later cleanup pass — see
`dispatch-platform/docs/` for the full engineering documentation set.

## Quick start

### 1. Backend

```bash
cd dispatch-platform/backend
cp .env.example .env        # then edit .env — at minimum set JWT_SECRET
npm install
npx prisma migrate dev
npx tsx prisma/seed.ts
npm run dev                 # http://localhost:8002/api/health
```

### 2. Worker mobile app

```bash
cd frontend
cp .env.example .env
# Point the app at your backend. If you're testing on a physical device via
# Expo Go, use your computer's LAN IP, not localhost:
#   EXPO_PUBLIC_BACKEND_URL=http://<your-lan-ip>:8002
npm install
npm start                   # scan the QR code with Expo Go
```

Dev login: any phone number, OTP `123456` (see `.env` `DEV_OTP_CODE`).

## Required environment variables

See `dispatch-platform/backend/.env.example` and `frontend/.env.example` for
the full, documented list with defaults. At minimum:

- Backend: `DATABASE_URL`, `JWT_SECRET` (required — the server refuses to
  start without them)
- Frontend: `EXPO_PUBLIC_BACKEND_URL`

## Known limitations

- **Expo Go SDK compatibility:** this project targets **Expo SDK 54**. If
  your installed Expo Go app is on a newer SDK (e.g. SDK 57), it may report a
  compatibility warning or fail to open the project. This is a known,
  intentionally deferred issue — do not upgrade the project's Expo SDK to
  work around it without a deliberate, separately-scoped migration.
- **Contractor/admin web apps do not exist yet.** See the scope note above.
- A longer, actively-maintained list of known gaps and shortcuts lives in
  [`dispatch-platform/docs/KnownLimitations.md`](dispatch-platform/docs/KnownLimitations.md) —
  read it before you spend time rediscovering something already documented
  there.

## Documentation

The full engineering documentation set — architecture, API reference,
database schema, the shift state machine, the dispatch/trust engines,
authentication, deployment, and known limitations — lives under
[`dispatch-platform/docs/`](dispatch-platform/docs/). Start with
[`dispatch-platform/docs/README.md`](dispatch-platform/docs/README.md).
