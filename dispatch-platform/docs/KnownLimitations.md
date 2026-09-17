# Known Limitations

Everything a Phase-1 MVP shortcut. This document is written for the engineer
who inherits the codebase — read it before you spend a day debugging one
of these on your own.

---

## 1. Runtime / infra

### 1.1 FastAPI reverse proxy (Emergent-only)
`/app/backend/server.py` is not a real service — it's a shim to make
Emergent's supervisor happy. It:
- Spawns the Node backend as a subprocess on port 8002 at startup.
- Forwards every `/api/*` to it.
- Has zero business logic.

**Delete this file** for any deployment outside Emergent. In VS Code you
just run the Node backend directly.

### 1.2 Backend is a single Node process
No clustering, no horizontal scaling primitives wired. Adequate for the
first ~500 concurrent workers. Add PM2 or K8s replicas once that ceiling
approaches. Session state is already stateless, so scaling is
work-not-code.

### 1.3 No offer expiry scheduler
Offers get an `expiresAt = now + 15 min` but nothing sweeps them from
`PENDING` to `EXPIRED`. They sit in the DB, filtered lazily on read/accept.
Cheap to fix — see `DispatchEngine.md` §6 for the one-liner.

### 1.4 No graceful shutdown
`server.ts` doesn't handle `SIGTERM` — an in-flight Prisma transaction on
a redeploy could be interrupted. Add:

```ts
process.on('SIGTERM', async () => {
  await prisma.$disconnect();
  server.close(() => process.exit(0));
});
```

### 1.5 SQLite in "prod"
Dev DB is SQLite. Prisma schema is Postgres-compatible but the
`provider = "sqlite"` line and the migrations under `prisma/migrations/`
are dialect-specific. `DeploymentGuide.md` §5 shows the migration path.

---

## 2. Authentication

### 2.1 OTP is a fixed dev constant
`DEV_OTP_CODE = "123456"` for every phone, every request. Prod hardening is
in `Authentication.md` §8. Do not leave this unchanged in production.

### 2.2 OTP echoed in the API response
`/api/auth/otp/request` returns `devOtp` in the response body so automated
tests can read it. The code strips it when `NODE_ENV === "production"` but
double-check on prod deploy.

### 2.3 OTP stored plaintext
The `Otp.code` column stores the raw code. Fine when the code is a public
constant. **Hash with bcrypt** when real per-request codes are generated.

### 2.4 No rate limits
`/otp/request` and `/otp/verify` are unbounded. A single attacker can burn
through the Otp table with a for-loop. Wire `express-rate-limit` before
public launch (`Authentication.md` §8).

### 2.5 JWT expiry is 30 days
Convenient in dev, too long in prod. Drop to 24h + refresh flow.

### 2.6 JWT secret is single-valued
No rotation support in code today. `DeploymentGuide.md` §7 documents the
two-secret pattern; implement it before the first rotation.

### 2.7 No 2FA for admins
Admin role uses the same phone + OTP flow as workers. Ship TOTP before any
external admin ever logs in.

---

## 3. Data model

### 3.1 Skills stored as a CSV string — first migration step landed in Patch 1
`Worker.skills` is `"MASON,HELPER,WELDER"`. Filter by `skills.contains(x)`.
Works because we have 10 skills. Migrate to a `WorkerSkill` join table
when we exceed ~30 or we need per-skill certification metadata.

Patch 1 / Milestone 0C added a real `Trade`/`Task`/`WorkerCapability`/
`Assessment` graph (see `CapabilityModel.md`) that is exactly the kind of
per-skill, leveled, evidenced model this note anticipated — but it runs
**beside** `Worker.skills`, not instead of it. `Worker.skills` is still the
only thing `DispatchEngine` reads; nothing migrates automatically between
the two systems yet.

### 3.2 Denormalised counters on `Worker`
`totalShifts`, `completedShifts`, `cancelledShifts`, `acceptedOffers`,
`declinedOffers`, `avgRating`, `totalEarnings` all live on the row. Writers
must remember to update them inside the same transaction as the underlying
change. If we forget once, trust score drifts silently. Long-term fix:
periodic recomputation job that reconciles counters from source-of-truth
tables.

### 3.3 `avgRating` is not recomputed
Ratings are declared in the schema but there's no `RatingService` yet, so
`Worker.avgRating` never actually changes. Trust weight for rating (15%)
effectively contributes 0 today.

### 3.4 No soft delete on most tables
Only `User` has `deletedAt`. Deleting a contractor cascades all their
projects/jobs/shifts. Add `deletedAt` to `Project`, `Job`, `Shift` before
GDPR "delete my account" flows.

### 3.5 Timezones assumed IST
`shiftDate` is stored as UTC but the seed and API use "shift date" as an
IST-aligned wall-clock date. If we expand outside IST, add a
`Project.timezone` column and convert on read.

### 3.6 `startTime`/`endTime` as string
Stored as `"HH:mm"` strings. Cheap to compare but non-typed. Consider
minutes-since-midnight int when we start querying by time-of-day.

### 3.7 `Rating.authorId` allows anyone
The `authorId` is a `User.id` foreign key with no role check at the DB
level. Enforce `role === CONTRACTOR` in the (future) `POST /shifts/:id/rating`
service.

---

## 4. Dispatch & shift logic

### 4.1 Workload factor is a constant
`DispatchEngine` blends four factors — but `workload = 1.0` for every
worker. See `DispatchEngine.md` §5 for the query pattern to replace it.

### 4.2 Dispatch fires only when the job is created
No re-dispatch on offer decline or expiry, no priority queue, no scheduler.
A job with 5 declines quickly runs out of candidates. Fix: after every
`declineOffer` (and once we add an expiry sweeper), call
`DispatchEngine.dispatchJob(jobId)` again if `job.status === 'DISPATCHING'`.

### 4.3 Geofence is fixed at 500 m
Small sites need tighter (~50 m); massive infrastructure sites need wider
(~1 km). Move `CHECKIN_MAX_KM` to `Project.geofenceMeters` and default to
500.

### 4.4 Overtime is impossible
`amountEarned = min(1.0, worked/scheduled) × wage`. A worker who stays two
hours late gets paid for the scheduled day. Fine for daily-wage workers,
wrong for hourly.

### 4.5 Cancellation is coded but not exposed
`ShiftEngine.canTransition(anyNonTerminal, 'CANCELLED')` returns true, but
no endpoint calls it. Cancellation flows must be built (`ShiftEngine.md` §7).

### 4.6 Two-shift-same-day is not blocked
A worker could theoretically accept two offers for overlapping times.
Add a `hasConflictingShift(workerId, date, start, end)` check in
`JobService.acceptOffer`.

### 4.7 No idempotency keys
POSTing accept twice creates one shift + one 4xx. Fine. But a mobile
double-tap can produce transient duplicates in rare cases. Add
`Idempotency-Key` header support before the first real launch.

---

## 5. Mobile

### 5.1 No offline mode
Every screen assumes network. If the user hits Accept in a low-signal area,
the tap silently fails and they might miss the offer window. Fix requires:
- Request queue with retry (redux-persist + a mutation queue).
- Optimistic UI for state transitions.

### 5.2 Foreground-only location
`expo-location` foreground only. Real dispatch benefits from the last-known
GPS being fresh; today it's only fresh on app foreground. Background
location requires a native build (out of Expo Go) and additional Play
Store review.

### 5.3 GPS accuracy trust
We trust `Location.getCurrentPositionAsync({ accuracy: High })` for check-in
enforcement. Emulator and jailbroken devices can spoof this. Once we have
scale, add server-side sanity checks (e.g. worker's home coords vs current
coords vs previous pings).

### 5.4 No push notifications
In-app `Notification` table only. Workers won't get offers unless they
open the app. Wire APN/FCM via `expo-notifications` in a native build; the
service seam already exists.

### 5.5 English-only UI
No i18n. Target market has many primary languages. Extract strings to an
`i18n/en.json` and swap for a real i18n library (i18next) at Phase 2.

### 5.6 No haptics on state transitions
On a construction site, a subtle vibration when the shift transitions
would be great UX. `expo-haptics` at every `ShiftService` call would take
30 minutes.

---

## 6. Contractor / Admin

### 6.1 Both portals are stubs
`contractor-web/` and `admin-web/` are empty folders (with README hints).
No contractor UI exists — a contractor can neither log in nor post a job
without direct API access. Phase 2/3.

### 6.2 Job creation isn't exposed as an endpoint yet
`JobService.createAndDispatch` exists but isn't wired to a route (there's
no `/api/contractor/jobs` router). Add before Phase 2 UI work.

### 6.3 No project CRUD
Projects are seeded but there's no way to create them via API. Same shape:
service exists, controller/route to add.

---

## 7. Testing

### 7.1 No unit tests in the repo
The testing agent wrote pytest integration tests at
`/app/backend/tests/test_dispatch_backend.py`; nothing in `backend/src/**`
has a `.test.ts` counterpart. Priority order:
1. Pure engines (`ShiftEngine`, geo helpers).
2. Services with transactions (`JobService.acceptOffer`).
3. Auth flow.

Recommended stack: `vitest` + `supertest` + in-memory SQLite.

### 7.2 No CI
No GitHub Actions yet. First workflow to add:
- `typecheck` (backend + mobile)
- `lint` (both)
- `test` (once vitest lands)

### 7.3 Seed depends on Math.random
Non-deterministic. If we start snapshotting fixtures for tests, replace
with a seeded RNG (e.g. `seedrandom`).

---

## 8. Ops

### 8.1 No metrics
No `/metrics` endpoint. No p95 latency history. Add `prom-client` at first
sign of load.

### 8.2 No structured logging
`morgan` + `console.log`. Move to `pino` with JSON output before shipping
logs to a real sink.

### 8.3 No error tracking
No Sentry. Wire it before the first external user.

### 8.4 No backups documented
Section 9 of `DeploymentGuide.md` mentions it — write the actual script.

---

## 9. Documented gotchas

- The **preview and production databases diverge** after the first deploy —
  Emergent-specific quirk. Reseed / migrate carefully.
- The `mobile` symlink in `dispatch-platform/mobile → /app/frontend` only
  exists in the Emergent workspace. On a plain checkout you either mirror
  the layout or edit `app/frontend/**` directly.
- The `checkInAt` calculation for `lateMinutes` uses **local server time**
  (`new Date().getHours()`), not the shift's timezone. Bug when the server
  is in UTC and the shift is in IST — `lateMinutes` will be off by 5:30.
  Fix by moving to `dayjs`/`luxon` with timezone support.

If you fix any of these, please also update this file.
