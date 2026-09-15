# Shift Engine

**File:** `backend/src/engines/shift.engine.ts`
**State column:** `Shift.state` (`String`, one of 13 constants in `types/domain.ts`).

A deterministic finite-state machine that governs the life of every shift.
Every transition is validated against the graph below; illegal moves throw
`AppError.invalidState(...)` → **HTTP 422**.

Every successful transition writes a `ShiftEvent` row so the timeline is
complete and auditable.

---

## 1. States

| State        | Meaning                                                              |
|--------------|----------------------------------------------------------------------|
| `CREATED`    | Shift row created; not yet offered. Rarely used (offers skip to `ACCEPTED`). |
| `OFFERED`    | Presented to the worker as a `JobOffer` (the shift row itself doesn't sit here in Phase 1). |
| `ACCEPTED`   | Worker tapped Accept. Wage is locked in.                             |
| `TRAVELLING` | Worker has left for the site.                                        |
| `ARRIVED`    | Worker declares arrival (not yet geofenced).                         |
| `CHECKED_IN` | GPS geofence validated (≤ 500 m). `checkInAt` captured; `lateMinutes` computed. |
| `WORKING`    | Actively working.                                                    |
| `BREAK`      | On a break.                                                          |
| `RESUMED`    | Resumed after a break (can loop back into `WORKING` / `BREAK`).      |
| `COMPLETED`  | Worker declared work finished — not yet checked out.                 |
| `CHECKED_OUT`| GPS check-out captured; worked-minutes and early-exit computed.      |
| `CLOSED`     | Terminal. Payment finalised, trust recomputed.                       |
| `CANCELLED`  | Terminal branch (any non-terminal state can move here).              |

---

## 2. Transition graph

```
CREATED     → OFFERED, CANCELLED
OFFERED     → ACCEPTED, CANCELLED
ACCEPTED    → TRAVELLING, CANCELLED
TRAVELLING  → ARRIVED, CANCELLED
ARRIVED     → CHECKED_IN, CANCELLED
CHECKED_IN  → WORKING, CANCELLED
WORKING     → BREAK, COMPLETED, CANCELLED
BREAK       → RESUMED, CANCELLED
RESUMED     → WORKING, BREAK, COMPLETED, CANCELLED
COMPLETED   → CHECKED_OUT
CHECKED_OUT → CLOSED
CLOSED      → (terminal)
CANCELLED   → (terminal)
```

Encoded in `shift.engine.ts` as `const TRANSITIONS: Record<ShiftStateT, ShiftStateT[]>`.

Two helper methods:
- `canTransition(from, to): boolean`
- `assertTransition(from, to): void` — throws `AppError.invalidState` on failure.

---

## 3. Attendance rules

### 3.1 Geofence (check-in / check-out)

`ShiftService.checkIn` and `checkOut` require latitude + longitude in the
body. The service computes Haversine distance to the parent project's
coordinates and rejects with `422 INVALID_STATE` if the distance exceeds
**`CHECKIN_MAX_KM = 0.5`** (500 m).

Extend for check-out with a larger radius if the site is huge; for now the
same 500 m applies to both events.

### 3.2 Lateness & early exit

- `lateMinutes = max(0, checkInMinutes - scheduledStartMinutes)`
- `earlyExitMinutes = max(0, scheduledEndMinutes - checkOutMinutes)`

Both are stored on the `Shift` row and used later by TrustEngine (via
`completedShifts` / `cancelledShifts` counters — not by the raw minutes today).

### 3.3 Worked minutes

Captured on `CHECKED_OUT`:
```
workedMinutes = round((checkOutAt - checkInAt) / 60_000)
```
No clamping — a shift that runs 30 minutes over the scheduled end
naturally accrues extra worked minutes.

---

## 4. Payment finalisation (on CLOSED)

```
scheduledMins = scheduledEnd - scheduledStart
workedMins    = shift.workedMinutes
ratio         = clamp(workedMins / scheduledMins, 0, 1)
amountEarned  = round(wageAmount × ratio)
```

Then, atomically:
- `Worker.completedShifts += 1`
- `Worker.totalEarnings += amountEarned`
- `TrustEngine.recompute(workerId)`

**Rationale:** `ratio` is capped at 1.0 — no overtime pay in Phase 1. When
overtime lands, extend to `ratio = workedMins / scheduledMins` (unclamped)
and multiply the overshoot by an `overtimeMultiplier`.

**Rationale for scheduled-minutes based prorate:** simpler than tracking
break minutes, and it aligns with how contractors negotiate daily wages in
the target market — you show up and put in the day, you get the daily rate;
you leave halfway, you get half.

---

## 5. Public API surface (in `ShiftService`)

Every method takes `(shiftId, workerUserId, ...)` and returns the updated
shift. Ownership is enforced: `shift.worker.userId === workerUserId` or `403`.

```ts
travel(id, userId, lat?, lng?)
arrive(id, userId, lat?, lng?)
checkIn(id, userId, lat, lng)       // lat/lng required
startWork(id, userId)
startBreak(id, userId)
resume(id, userId)
complete(id, userId)
checkOut(id, userId, lat, lng)      // lat/lng required
close(id, userId)
```

They all funnel through one private helper:

```ts
private static async transition(
  shiftId, workerUserId, to,
  opts: { lat?, lng?, note? } = {},
)
```

That's the single choke point where you'd add:
- pre-transition hooks (validation, notifications)
- post-transition hooks (websocket push, analytics events)
- audit logging beyond the ShiftEvent row

---

## 6. `ShiftEvent` audit log

Every transition writes:

```ts
{
  shiftId,
  fromState,
  toState,
  latitude?,   // GPS if provided
  longitude?,
  note?,
  createdAt: now
}
```

The mobile app's Shift Detail screen renders these as a timeline.

Never delete `ShiftEvent` rows. If a shift is force-cancelled or wiped by
an admin, keep the audit trail — soft delete the `Shift` instead when we
add that flag.

---

## 7. Cancellation (not yet exposed)

`ShiftEngine.canTransition(anyNonTerminal, 'CANCELLED') === true` but there's
no route handler yet. Add two endpoints in Phase 2 / 3:

- `POST /api/worker/shifts/:id/cancel` — worker gives up (increments
  `Worker.cancelledShifts`, dings trust score).
- `POST /api/contractor/shifts/:id/cancel` — contractor cancels
  (increments a separate `Job.cancelledByContractor` counter, no trust ding).

Both should:
- transition the shift to `CANCELLED`
- write a `ShiftEvent` with a `note` explaining why (require a reason string)
- if the shift had `checkInAt`, still finalise partial pay (call the same
  proration logic as CLOSED)
- open a hole in `Job.headcount` and re-dispatch to fill it

---

## 8. Extension roadmap

- **Overtime / undertime pay bands** — extend prorate formula.
- **Two-person check-in** — require both worker GPS *and* a supervisor QR
  scan for high-value jobs.
- **Break duration limit** — auto-transition `BREAK → RESUMED` after 30
  minutes, or auto-cancel after 2 h.
- **Shift split** — a worker starts, hands off to another (rare but
  requested); handle by CANCEL + re-dispatch.
- **Pause reasons** — extend `BREAK` with a `reason` field (tea, safety, weather).

---

## 9. Testing recipe

The engine is trivially unit-testable — it's pure. A minimal suite:

```ts
describe('ShiftEngine', () => {
  test('canTransition: ACCEPTED → TRAVELLING', () =>
    expect(ShiftEngine.canTransition('ACCEPTED', 'TRAVELLING')).toBe(true));

  test('cannot skip states', () =>
    expect(ShiftEngine.canTransition('ACCEPTED', 'CHECKED_IN')).toBe(false));

  test('terminal states are terminal', () => {
    expect(ShiftEngine.canTransition('CLOSED', 'ACCEPTED')).toBe(false);
    expect(ShiftEngine.canTransition('CANCELLED', 'WORKING')).toBe(false);
  });

  test('assertTransition throws on illegal', () =>
    expect(() => ShiftEngine.assertTransition('WORKING', 'CLOSED'))
      .toThrow(/Illegal shift transition/));
});
```

The `ShiftService` is harder to unit test because it hits Prisma; use an
integration test that spins up an in-memory SQLite and drives the full
lifecycle for one shift.
