# Architecture

Complete architectural overview of the Dispatch Platform.

---

## 1. Product architecture

The platform has three clients backed by a **single** REST backend:

```
                 ┌────────────────────┐
                 │   Worker Mobile    │  Expo · React Native · TypeScript
                 │   (Android-first)  │  (Phase 1 — shipped)
                 └─────────┬──────────┘
                           │
                           │  HTTPS  /api/*
                           ▼
┌────────────────┐   ┌──────────────────────┐   ┌────────────────┐
│ Contractor Web │──▶│  Dispatch Backend     │◀──│  Admin Web     │
│ React · Vite   │   │  Node · Express · TS  │   │ React · Vite   │
│ (Phase 2)      │   │  Prisma ORM           │   │ (Phase 3)      │
└────────────────┘   └──────────┬───────────┘   └────────────────┘
                                │
                                ▼
                       ┌──────────────────┐
                       │  SQLite (dev)    │
                       │  PostgreSQL (prod)│
                       └──────────────────┘
```

All three clients speak the **same** REST API. No client contains business logic
— every rule (dispatch scoring, shift transitions, trust math) lives in
backend services and engines.

---

## 2. Backend layered architecture

```
HTTP Request
    │
    ▼
┌─────────────────────────────┐
│ Route      routes/*.ts      │  Express Router; declarative binding
├─────────────────────────────┤
│ Middleware auth, validate,  │  JWT verify · Zod schemas · error handler
│            error            │
├─────────────────────────────┤
│ Controller controllers/*.ts │  HTTP glue only — read req.body, call service,
│                             │  return json. No conditionals beyond guard clauses.
├─────────────────────────────┤
│ Service    services/*.ts    │  Business logic, orchestration, transactions.
│                             │  Throws AppError on invariants.
├─────────────────────────────┤
│ Engine     engines/*.ts     │  Pure domain logic: DispatchEngine, ShiftEngine,
│                             │  TrustEngine. No HTTP concepts.
├─────────────────────────────┤
│ Repository (via Prisma)     │  Data access — currently Prisma calls inline
│                             │  in services; extract to real repositories
│                             │  when persistence complexity grows.
├─────────────────────────────┤
│ Prisma Client               │  Typed SQL builder / migrations
└─────────────────────────────┘
```

**SOLID discipline enforced:**
- Controllers are 5-20 lines and delegate to a service.
- Services own transactions (`prisma.$transaction`) so multi-write flows are atomic.
- Engines are pure — no I/O — so they're trivially unit-testable when we add tests.
- Utilities (`utils/geo.ts`, `utils/jwt.ts`, `utils/errors.ts`) hold cross-cutting helpers.

---

## 3. Monorepo layout

```
dispatch-platform/
├── backend/                    # PRIMARY — Node/Express/TS
│   ├── src/
│   │   ├── config/             # env loader, prisma singleton
│   │   ├── controllers/        # HTTP handlers
│   │   ├── engines/            # Dispatch, Shift, Trust (pure logic)
│   │   ├── middleware/         # auth, validate, error
│   │   ├── repositories/       # (reserved — currently empty)
│   │   ├── routes/             # Express routers
│   │   ├── services/           # business logic
│   │   ├── types/              # domain enums
│   │   ├── utils/              # geo, jwt, errors
│   │   └── server.ts           # entrypoint
│   ├── prisma/
│   │   ├── schema.prisma       # single source of truth for data model
│   │   ├── migrations/
│   │   └── seed.ts             # deterministic seed generator
│   ├── package.json
│   ├── tsconfig.json
│   ├── .env.example
│   └── dev.db                  # SQLite (gitignored in prod)
│
├── mobile/                     # → symlink to /app/frontend (Expo)
├── contractor-web/             # Phase 2 (empty)
├── admin-web/                  # Phase 3 (empty)
├── shared/
│   └── types.ts                # cross-project domain types
├── docker/
│   └── README.md               # skeleton Dockerfile + docker-compose shape
├── docs/                       # this documentation set
└── README.md
```

---

## 4. Emergent runtime peculiarity (dev only)

Because Emergent's `supervisor` process manager hardcodes
`uvicorn server:app` on port 8001 for the `backend` program, we cannot swap
that command from the code side. Solution:

- `/app/backend/server.py` is a **thin FastAPI reverse proxy**. On startup it
  spawns the Node backend as a subprocess (`npx tsx watch src/server.ts` in
  `/app/dispatch-platform/backend`) on port **8002** and forwards every
  `/api/*` request to it (transparent to the client).
- The proxy is stateless. It contains **no business logic** and its only
  purpose is to appease the Emergent supervisor. Delete it entirely for a
  local / production deployment.
- If the Node subprocess dies, the proxy transparently respawns it on the
  next incoming request.

In a normal VS Code / docker-compose deployment:
```
Client → Node backend (port 8002)
```
No Python. No proxy. See `DeploymentGuide.md`.

---

## 5. Request lifecycle (worker accepts an offer)

1. Mobile posts `POST /api/jobs/offers/accept` with the offer id and a bearer JWT.
2. Express hits `middleware/auth.ts` — token verified, `req.auth = { sub, role, phone }`.
3. Route dispatches to `JobController.acceptOffer` which calls `JobService.acceptOffer`.
4. Service performs a Prisma `$transaction`:
   - Move the accepted offer to `ACCEPTED`
   - Auto-decline the worker's other pending offers on the same job
   - Insert a `Shift` row in state `ACCEPTED`
   - Insert a `ShiftEvent` for the OFFERED → ACCEPTED transition
   - Increment `Worker.acceptedOffers` and `Worker.totalShifts`
5. Post-transaction (outside the tx to avoid holding locks):
   - If `Job.headcount` is now met, flip `Job.status = FULFILLED` and expire outstanding offers
   - `TrustEngine.recompute(workerId)` — refreshes `Worker.trustScore`
6. Return `{ shift, offer }` as JSON.

Every write path uses this shape: **guard → transaction → post-processing**.

---

## 6. Concurrency & consistency model

- **Single Node process** in Phase 1; horizontal scaling requires session stickiness
  or a Redis-backed rate limiter. The DB is the source of truth.
- **Prisma transactions** wrap any multi-write action (offer accept, shift close).
- **Job overbooking guard** — before writing the `Shift` we re-check
  `shift.count({ where: { jobId } }) >= job.headcount` and reject with
  409 CONFLICT if the job filled up between offer creation and acceptance.
- **Offer TTL** — every offer has an `expiresAt` (15 min). The MVP relies on
  lazy expiry (checked on read/accept). See `KnownLimitations.md` for a
  scheduler note.

---

## 7. Security posture

- JWT (HS256) issued after OTP verify; 30-day expiry by default.
- `helmet()` sets standard security headers.
- CORS allow-list configurable via `CORS_ORIGIN`.
- Zod validation on every request body (both shape and value constraints).
- Role checks via `requireRole(...)` middleware — a WORKER token cannot hit
  contractor/admin routes.
- No PII in JWT payload beyond phone (used for audit-log correlation).
- OTP is a fixed dev constant. Prod hardening in `Authentication.md`.

---

## 8. Extension seams

The following are already coded as clean seams for later work:
- `services/notification.service.ts` — in-app only today; add an
  Expo/APN/FCM adapter behind the same service.
- `engines/dispatch.engine.ts` — scoring weights are literals in one place;
  ship them to env for A/B testing.
- `services/shift.service.ts` — the `transition(...)` helper is the single
  choke point for every state change; add before/after hooks there.
- `prisma/schema.prisma` — swap `provider = "sqlite"` to `"postgresql"` and
  add a new migration to go to prod.

---

## 9. Non-goals for Phase 1

- No websockets / SSE — polling for MVP.
- No file uploads — no ID docs, no site photos yet.
- No offline-first mobile — assumes network on the site.
- No multi-tenant contractor isolation beyond `contractorId` FK check in queries.
