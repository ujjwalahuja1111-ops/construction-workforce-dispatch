# Trust Engine

**File:** `backend/src/engines/trust.engine.ts`
**Persisted on:** `Worker.trustScore` (0..100 int).

Trust is the platform's reputation currency. It biases dispatch toward
reliable workers and gives new workers a fair cold-start.

---

## 1. Contract

```ts
TrustEngine.recompute(workerId: string): Promise<number>
```

Reads the worker's denormalised counters, applies the formula below, clamps
to `[0, 100]`, persists to `Worker.trustScore`, returns the new score.

Called from:
- `JobService.acceptOffer` (worker accepts).
- `JobService.declineOffer` (worker declines).
- `ShiftService.close` (a shift closes — the biggest signal).

---

## 2. Formula

```
attendance  = completedShifts / totalShifts                # 0..1
acceptance  = acceptedOffers / (acceptedOffers + declinedOffers)   # 0..1 or 0.5 if zero
reliability = 1 - (cancelledShifts / totalShifts)          # 0..1
rating      = avgRating / 5                                # 0..1

score = clamp(
  attendance   × 40
+ acceptance   × 25
+ reliability  × 20
+ rating       × 15
, 0, 100)
```

Weights total 100 — the raw score is already in the target range; `clamp`
guards against float drift or negative reliability from bad data.

---

## 3. Cold-start

Workers with `totalShifts === 0` get a fixed baseline:

```ts
if (worker.totalShifts === 0) {
  score = 70;
}
```

**Why 70?** It sits above the "risky" threshold (60) so a new worker still
gets dispatched, but below the "excellent" cutoff (80) so they're behind
proven workers when both are equally available. As the worker completes
shifts, the formula takes over.

---

## 4. Interpretation buckets (used by the UI)

| Range   | Label       | Colour             |
|---------|-------------|--------------------|
| 80–100  | Excellent   | success green      |
| 60–79   | Good        | warning amber      |
| 0–59    | Low         | danger red         |

These are display-only — the DispatchEngine reads the raw score, not the
bucket.

---

## 5. Design notes

### Why denormalised counters?

We store `completedShifts`, `cancelledShifts`, `acceptedOffers`, `declinedOffers`,
`avgRating` directly on the `Worker` row. Alternatives considered:

- **Compute on read** — issues one aggregate query per worker per dispatch
  scoring, would kill Postgres under load once we have thousands of workers.
- **Materialised view** — Postgres-only, refresh lag is a foot-gun on
  fairness (a just-completed shift wouldn't count for the next dispatch).

The denormalised counters have a small write cost (one row-update inside an
existing transaction) and read as fast as the primary key.

### Why linear, not logarithmic?

The formula is linear in each factor. A worker at 100% attendance across 3
shifts and a worker at 100% across 300 shifts get the same attendance
factor. This is intentional — the marketplace already surfaces experience
through the `experienceYears` field in the profile; trust is meant to signal
**recent behaviour**, not seniority.

If cold-start abuse becomes a problem ("I just completed 1 shift, give me
full trust"), replace with a Wilson score interval or a Bayesian smoothing:

```
attendance = (completedShifts + 5) / (totalShifts + 10)
```

That biases the score toward 0.5 until enough shifts accumulate.

### Why acceptance in trust?

Acceptance rate is included because chronic decliners waste dispatch cycles
— every declined offer is a lost minute the contractor can't afford. But
the weight (25) is intentionally lower than attendance (40) since declining
an offer you can't do is far less bad than accepting one you don't show up
for.

---

## 6. Tuning

Weights are hardcoded literals in `trust.engine.ts`. Recommended pattern
when the admin portal ships:

```prisma
model Config {
  key   String @id
  value String  // JSON string
}
```

Then read the weights at startup with a cache:

```ts
const weights = await getConfigJson('trust.weights', {
  attendance: 40, acceptance: 25, reliability: 20, rating: 15,
});
```

Emit a `configChanged` event when admins change values so the cache invalidates.

---

## 7. Fraud / abuse mitigation

The formula is naive today. Known attack vectors:

1. **Self-cancel farming** — a worker accepts, checks in with a spoofed GPS,
   sits at home. Mitigation: contractor-side check-in confirmation OR
   photo-of-worker attestation at check-in (Phase 2+).
2. **Offer flood decline** — a worker with `isAvailable=true` who declines
   everything won't tank their trust much (25% weight). Mitigation: add a
   "recent decline rate" (last 30 days only) to give the signal more punch.
3. **Rating collusion** — a friendly contractor rates 5 stars every time.
   Mitigation: normalise ratings per contractor before averaging (subtract
   the contractor's mean rating from their own score before adding to the
   worker's).

None of these are in scope for Phase 1 but are worth flagging.

---

## 8. Trust score UI (Mobile — `/trust`)

The mobile app shows:
- Big ring with the numeric score.
- Chip: Excellent / Good / Low.
- 4 factor rows: Attendance (X/Y shifts), Acceptance (%), Cancellations
  (count), Avg rating (out of 5).

Everything is derived from the same counters the engine uses — no separate
API call, just `worker.*` fields off `/worker/me`.

---

## 9. Testing recipe

The engine is deterministic — one worker id in, one number out. Fixtures:

| Case                                        | Expected |
|---------------------------------------------|----------|
| totalShifts=0                               | 70       |
| 10/10 completed, 10/10 accepted, 0 cancel, 5.0 rating | 100      |
| 0/10 completed, 0/10 accepted, 10 cancel, 0 rating    | 0        |
| 8/10, 7/10, 2/10, 4.0                       | 76       |

Directly test the pure math without touching Prisma by extracting a
`computeScore(counters) -> number` helper.
