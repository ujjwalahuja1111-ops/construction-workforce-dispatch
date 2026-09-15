# Dispatch Engine

**File:** `backend/src/engines/dispatch.engine.ts`

Given a `Job`, produce a ranked shortlist of workers and create `JobOffer`
rows for the top N.  This is the piece of code that decides who gets the
next job — it's the marketplace's matching brain.

---

## 1. Contract

```ts
DispatchEngine.dispatchJob(jobId: string): Promise<{
  offersCreated: number,
  remaining: number,       // headcount not yet filled
  candidates?: number,
}>
```

Behaviour:
1. Load the job with `project`, existing `offers`, existing `shifts`.
2. Reject if job status is not `OPEN` or `DISPATCHING`.
3. Compute `remaining = headcount - shifts.length`; return early if `<= 0`.
4. Query workers matching the filters below.
5. Score, rank, cap.
6. In a transaction: insert `JobOffer` rows + a `Notification` per offer,
   flip job status to `DISPATCHING`.

Called from:
- `JobService.createAndDispatch` when a contractor posts a new job.
- (Future) a scheduler when previous offers expire without filling the job.
- (Future) admin "re-dispatch" action.

---

## 2. Candidate filters (hard)

A worker is eligible only if **all** of:

- `worker.isAvailable === true`
- `worker.skills` (CSV) contains the job's skill code
- `worker.id` is not already in an existing offer for this job
- Haversine distance ≤ `env.dispatchMaxRadiusKm` (default **25 km**)

Skill match is `contains` on the CSV. That's fine when we have 10 skills; if
we grow to hundreds move to a `WorkerSkill` join table with an index.

---

## 3. Scoring (soft)

The score is a weighted blend of four normalised factors, each in `[0, 1]`:

```
score = trust      × 0.35
      + acceptance × 0.20
      + distance   × 0.30
      + workload   × 0.15
```

| Factor      | Formula                                                | Notes                        |
|-------------|--------------------------------------------------------|------------------------------|
| trust       | `worker.trustScore / 100`                              | See `TrustEngine.md`         |
| acceptance  | `accepted / (accepted + declined)`                     | Falls back to `0.5` when no offer history |
| distance    | `1 - distanceKm / maxRadiusKm`                         | Linear decay 1 → 0 across the radius |
| workload    | Currently a constant `1.0`                             | Placeholder; see §5          |

Top candidates (up to `min(env.dispatchMaxCandidates, remaining * 3)`, default
`min(15, remaining * 3)`) receive offers, each with a 15-minute TTL.

---

## 4. Distance source (per worker, in order)

The engine uses the freshest known location for each worker:
1. `currentLatitude` / `currentLongitude` (last GPS ping from the mobile app).
2. Fallback: `homeLatitude` / `homeLongitude` (declared at registration).
3. If neither exists, distance is `+Infinity` → filtered out.

Refresh path: the worker's app opportunistically calls
`POST /api/worker/location` on foreground; contractors thus get warmer data
when they post at 6:30 am than at 3 pm.

---

## 5. Workload factor (intentional stub)

Set to `1.0` for every worker in Phase 1. This is where you'd implement:
- "penalise if worker has another shift today"
- "penalise if worker is currently `WORKING` on another job" (shouldn't happen
  but defence-in-depth)
- "penalise below-target-hours workers less" (fairness)

Add a query like:
```ts
const activeToday = await prisma.shift.count({
  where: { workerId: w.id, shiftDate: sameDay(job.shiftDate),
           state: { notIn: ['CLOSED', 'CANCELLED'] } },
});
const workload = activeToday === 0 ? 1 : 0.3;
```

---

## 6. Offer TTL and lifecycle

- `expiresAt = now + 15 min` at creation.
- When a worker taps Accept, the accept flow validates `expiresAt > now`;
  otherwise the offer is force-moved to `EXPIRED` and the accept fails.
- **No background job expires offers today** — they just sit in `PENDING`
  and get lazily filtered. See `KnownLimitations.md` for the scheduler note.

To add a cron:
```ts
// backend/src/jobs/expire-offers.ts
setInterval(async () => {
  await prisma.jobOffer.updateMany({
    where: { status: 'PENDING', expiresAt: { lt: new Date() } },
    data: { status: 'EXPIRED' },
  });
}, 60_000);
```

---

## 7. Fulfilment cascade

Handled outside the engine, in `JobService.acceptOffer`:
- On accept, `Worker.acceptedOffers++` and `Worker.totalShifts++`.
- If the accept brings us to `Job.headcount`, flip `Job.status = FULFILLED`
  and mass-expire pending offers.
- The DispatchEngine can be called again for the same job while its status
  is `DISPATCHING` (e.g. an offer was declined and we want to top up). It
  intentionally excludes workers already offered.

---

## 8. Tuning

The four weights and the radius are hardcoded literals in `dispatch.engine.ts`
and `env.dispatchMaxRadiusKm`. When the admin portal ships (`Admin.md` §3.10),
lift them into a `Config` table and expose sliders. Until then, edit in code
and redeploy.

**Heuristics from stakeholder feedback (not yet validated with real data):**
- Trust weight should dominate — a mediocre worker at 500 m is worse than a
  reliable one 5 km away.
- Distance should be a hard cap **before** the score, not a soft penalty,
  when the site is > 25 km away (workers won't travel).
- Acceptance rate cold-start `0.5` is intentional: cold-start workers shouldn't
  be punished for having no history.

---

## 9. Extension seams

- **Contract**: `dispatchJob(jobId)` is the only public surface. Add
  `dispatchJobs(jobIds[])` when batch operations arrive.
- **Scoring**: extract to `scoreCandidate(worker, job) -> number` for unit
  testing.
- **Filters**: extract to `candidateFilter(worker, job) -> boolean` — you'll
  want this once we add "skill certifications", "age restrictions",
  "language matching".
- **Persistence**: the transaction that writes offers + notifications is the
  right seam to hook a websocket push later.

---

## 10. Unit test recipe (when you write tests)

Fixtures:
- 5 workers: identical trust/acceptance, varying distance (1 km, 5 km, 15 km,
  25 km, 30 km) → assert ordering + the 30 km worker is filtered.
- 3 workers: identical distance, varying trust (60/70/90) → assert ordering.
- 2 workers, same trust and distance, different acceptance rates → assert
  ordering.

Mock Prisma using `prisma-mock` or `@prisma/client`'s manual mocking pattern.
The engine is pure enough that a lightweight `PrismaClient` stub with
`worker.findMany`, `jobOffer.create`, `notification.create`, `job.update`,
`$transaction` is sufficient.
