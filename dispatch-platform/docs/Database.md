# Database

Single source of truth: `backend/prisma/schema.prisma`.

**Dev DB:** SQLite (file: `backend/dev.db`).
**Prod-compatible target:** PostgreSQL (change one line, see §7).

---

## 1. Design principles

- **UUIDv4 primary keys** — no autoincrement, safe to merge shards later.
- **`createdAt` / `updatedAt`** on every mutable row via `@default(now())` /
  `@updatedAt`.
- **Soft deletes** — `deletedAt DateTime?` on `User` (only user is soft-deletable
  in Phase 1; extend to Worker / Contractor when GDPR flows land).
- **Enums as `String`** — SQLite has no native enums; validated at the app layer
  via `types/domain.ts`. Trivial to swap for `enum` when we move to Postgres.
- **Indexes** on every foreign key that participates in a hot query path plus
  `@@unique` composite constraints on natural keys (`Offer(jobId, workerId)`).
- **Denormalised counters** on `Worker` (`trustScore`, `totalShifts`,
  `acceptedOffers`, …) — recomputed by TrustEngine on write, not on read.

---

## 2. Entity overview

```
User (1) ─── (0/1) Worker
User (1) ─── (0/1) Contractor
User (1) ─── (*)   Otp
User (1) ─── (*)   Notification
User (1) ─── (*)   Rating (as author)

Contractor (1) ─── (*) Project
Project    (1) ─── (*) Job
Job        (1) ─── (*) JobOffer
Job        (1) ─── (*) Shift

Worker (1) ─── (*) JobOffer
Worker (1) ─── (*) Shift
Worker (1) ─── (*) Rating

Shift  (1) ─── (*) ShiftEvent
Shift  (1) ─── (0/1) Rating
```

---

## 3. Models

### `User`
Single account per phone. Role decides which profile row is expected.

| Field       | Type      | Notes                                     |
|-------------|-----------|-------------------------------------------|
| id          | uuid      | PK                                        |
| phone       | string    | **unique**, E.164 format (`+91XXXXXXXXXX`)|
| role        | string    | `WORKER` \| `CONTRACTOR` \| `ADMIN`       |
| fullName    | string    |                                           |
| isVerified  | bool      | flipped true after first OTP verify       |
| isActive    | bool      |                                           |
| deletedAt   | datetime? | soft-delete marker                        |
| createdAt   | datetime  |                                           |
| updatedAt   | datetime  |                                           |

Indexes: `role`, `phone`.

### `Otp`
One-time codes issued by AuthService.

| Field     | Type     | Notes                             |
|-----------|----------|-----------------------------------|
| id        | uuid     | PK                                |
| userId    | uuid     | FK → User (cascade)               |
| code      | string   | 6-digit numeric (dev = `123456`)  |
| expiresAt | datetime | now + `OTP_TTL_SECONDS`           |
| consumed  | bool     | set true on successful verify     |
| createdAt | datetime |                                   |

Index: `userId`.

### `Worker`
Worker profile + denormalised trust counters.

| Field              | Type      | Notes                                  |
|--------------------|-----------|----------------------------------------|
| id                 | uuid      | PK                                     |
| userId             | uuid      | FK → User (unique, cascade)            |
| skills             | string    | CSV of skill codes                     |
| experienceYears    | int       |                                        |
| dailyWage          | int       | INR (default 0)                        |
| city, state        | string    |                                        |
| homeLatitude/Lng   | float?    | worker's declared home                 |
| currentLatitude/Lng| float?    | last known GPS ping                    |
| isAvailable        | bool      | dispatcher only offers if true         |
| trustScore         | int       | 0–100                                  |
| totalShifts        | int       |                                        |
| completedShifts    | int       |                                        |
| cancelledShifts    | int       |                                        |
| acceptedOffers     | int       |                                        |
| declinedOffers     | int       |                                        |
| avgRating          | float     | 0..5                                   |
| totalEarnings      | int       | INR lifetime                           |
| createdAt/updatedAt| datetime  |                                        |

Indexes: `city`, `isAvailable`, `trustScore`.

### `Contractor`
| Field       | Type   | Notes                            |
|-------------|--------|----------------------------------|
| id          | uuid   | PK                               |
| userId      | uuid   | FK → User (unique, cascade)      |
| companyName | string |                                  |
| city, state | string |                                  |
| gstNumber   | string?|                                  |
| rating      | float  | 0..5 (from worker feedback)      |

Index: `city`.

### `Project`
A construction site owned by one contractor.

| Field       | Type      | Notes                                    |
|-------------|-----------|------------------------------------------|
| id          | uuid      | PK                                       |
| contractorId| uuid      | FK → Contractor (cascade)                |
| name        | string    |                                          |
| siteAddress | string    |                                          |
| city, state | string    |                                          |
| latitude    | float     | used for dispatch distance + geofence    |
| longitude   | float     |                                          |
| startsOn    | datetime  |                                          |
| endsOn      | datetime? |                                          |
| status      | string    | `ACTIVE` \| `PAUSED` \| `COMPLETED`      |

Indexes: `contractorId`, `city`.

### `Job` — a labour request
N workers of a given skill needed on a given date.

| Field      | Type     | Notes                                       |
|------------|----------|---------------------------------------------|
| id         | uuid     | PK                                          |
| projectId  | uuid     | FK → Project (cascade)                      |
| skill      | string   | one of `Skill` codes                        |
| headcount  | int      | total workers needed                        |
| dailyWage  | int      | INR per worker per day                      |
| shiftDate  | datetime | the day workers are required                |
| startTime  | string   | `"HH:mm"` (24-h)                            |
| endTime    | string   | `"HH:mm"`                                   |
| status     | string   | `OPEN` \| `DISPATCHING` \| `FULFILLED` \| … |
| notes      | string?  |                                             |

Indexes: `status`, `shiftDate`, `skill`.

### `JobOffer` — dispatch decision to a specific worker
| Field      | Type     | Notes                                       |
|------------|----------|---------------------------------------------|
| id         | uuid     | PK                                          |
| jobId      | uuid     | FK → Job (cascade)                          |
| workerId   | uuid     | FK → Worker (cascade)                       |
| status     | string   | `PENDING` \| `ACCEPTED` \| `DECLINED` \| `EXPIRED` |
| score      | float    | 0..1, used for ranking (see DispatchEngine.md) |
| distanceKm | float    | computed via Haversine                      |
| expiresAt  | datetime | now + 15 min                                |
| respondedAt| datetime?|                                             |

Constraints:
- **`@@unique([jobId, workerId])`** — a worker can only be offered a job once.
- Indexes: `(workerId, status)`, `(jobId, status)`.

### `Shift` — the accepted work unit
Driven by ShiftEngine's state machine.

| Field             | Type     | Notes                                     |
|-------------------|----------|-------------------------------------------|
| id                | uuid     | PK                                        |
| jobId             | uuid     | FK → Job (cascade)                        |
| workerId          | uuid     | FK → Worker (cascade)                     |
| state             | string   | see `ShiftEngine.md`                      |
| shiftDate         | datetime | copied from Job at accept                 |
| scheduledStart/End| string   | `"HH:mm"`                                 |
| checkInAt         | datetime?| when the worker actually checked in       |
| checkInLat/Lng    | float?   | captured GPS                              |
| checkOutAt        | datetime?|                                           |
| checkOutLat/Lng   | float?   |                                           |
| wageAmount        | int      | locked in at accept                       |
| lateMinutes       | int      | scheduledStart → checkInAt (≥ 0)          |
| earlyExitMinutes  | int      | checkOutAt → scheduledEnd (≥ 0)           |
| workedMinutes     | int      |                                           |
| amountEarned      | int      | finalized on CLOSE                        |

Indexes: `(workerId, state)`, `jobId`, `shiftDate`.

### `ShiftEvent` — audit log
Append-only row per state transition.

| Field      | Type     | Notes                        |
|------------|----------|------------------------------|
| id         | uuid     | PK                           |
| shiftId    | uuid     | FK → Shift (cascade)         |
| fromState  | string   |                              |
| toState    | string   |                              |
| note       | string?  |                              |
| latitude   | float?   |                              |
| longitude  | float?   |                              |
| createdAt  | datetime |                              |

Index: `shiftId`.

### `Rating`
One per completed shift.

| Field    | Type    | Notes                                       |
|----------|---------|---------------------------------------------|
| id       | uuid    | PK                                          |
| shiftId  | uuid    | FK → Shift (unique — one rating per shift)  |
| workerId | uuid    | FK → Worker                                 |
| authorId | uuid    | FK → User (contractor user)                 |
| score    | int     | 1..5                                        |
| comment  | string? |                                             |

Index: `workerId`.

### `Notification`
In-app only for MVP.

| Field   | Type      | Notes                                            |
|---------|-----------|--------------------------------------------------|
| id      | uuid      | PK                                               |
| userId  | uuid      | FK → User                                        |
| type    | string    | `JOB_OFFER` \| `SHIFT_UPDATE` \| `RATING` \| `SYSTEM` |
| title   | string    |                                                  |
| body    | string    |                                                  |
| data    | string?   | JSON blob (e.g. `{ jobId, offerId }`)            |
| readAt  | datetime? | null = unread                                    |

Index: `(userId, readAt)`.

---

## 4. Cascading deletes

All child rows use `onDelete: Cascade`. Deleting a Contractor deletes its
Projects → Jobs → Offers → Shifts → ShiftEvents/Ratings.  This is safe in
Phase 1 because we don't yet have external references (no payment ledger,
no external audit trail). Once we do, switch specific relations to
`onDelete: Restrict` and rely on soft-delete instead.

---

## 5. Denormalised counters

Kept on `Worker` for fast reads:

- `totalShifts`, `completedShifts`, `cancelledShifts`
- `acceptedOffers`, `declinedOffers`
- `avgRating`, `totalEarnings`
- `trustScore`

The **only** writers are:
- `JobService` (increments accepted/declined and totalShifts)
- `ShiftService` (increments completedShifts and totalEarnings on CLOSE)
- `TrustEngine.recompute()` (writes `trustScore`)

If you add a new writer, keep it inside a Prisma transaction.

---

## 6. Migrations

Every change to `schema.prisma` must be paired with a migration:

```bash
# after editing schema.prisma
npx prisma migrate dev --name descriptive_change_name
```

The `prisma/migrations/` folder is the source of truth for the DB shape and
must be committed to git. Never edit an old migration — write a new one.

To reset (drop everything and re-seed):
```bash
npx prisma migrate reset --force
npx tsx prisma/seed.ts
```

---

## 7. Switching to PostgreSQL

Two changes:

1. **`schema.prisma`**
   ```prisma
   datasource db {
     provider = "postgresql"
     url      = env("DATABASE_URL")
   }
   ```
2. **`.env`**
   ```
   DATABASE_URL=postgresql://user:pass@host:5432/dispatch
   ```
3. `rm -rf prisma/migrations && npx prisma migrate dev --name init`
   *(or keep SQLite migrations and re-generate for Postgres — SQLite dialect
   is compatible for our schema but a fresh migration is cleaner.)*

Postgres-only upgrades we should adopt at that point:
- Native `enum` types for `role`, `state`, `status` columns.
- `citext` for `phone` (case-insensitive uniqueness, though phone is digits only).
- `PostGIS` geometry column on `Project.geo` for `ST_DWithin` — replaces
  in-memory Haversine for city-scale scans.
- Partial indexes: `CREATE INDEX ... WHERE status = 'PENDING'` for offers.

---

## 8. Seed data

`prisma/seed.ts` is fully deterministic-ish (uses `Math.random` for jitter but
seeds the volumes and IDs mentioned in `test_credentials.md`).

Volumes:
- 2 admins, 5 contractors, 10 workers
- 5 projects across Bengaluru / Mumbai / Delhi
- 10 jobs across 4 skill families and 4 days
- 3 pending offers pre-created for the demo worker `+919020001000`
- 1 closed shift for `+919020001001` (populates earnings/history views)

Idempotent — running `seed.ts` again wipes all data first (`deleteMany` on
every table in dependency order) and reinserts.
