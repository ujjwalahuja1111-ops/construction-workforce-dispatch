# Shift / Execution

**Status:** Landed on the Python backend (`backend-py/`) as the third real slice of the redesigned
product loop: `POST /api/dispatch-positions/{id}/execution`, `GET /api/executions/{id}`,
`POST /api/executions/{id}/check-in`, `POST /api/executions/{id}/start`,
`POST /api/executions/{id}/complete`. Builds directly on `docs/Dispatch.md`'s COMMITTED
DispatchPosition — nothing there was redone, only extended. Nothing in the legacy TypeScript backend
(`Job`, `JobOffer`, `Shift`, `ShiftEngine`) changed.

## The product loop this adds

```
COMMITTED DispatchPosition (existing, unchanged)
    -> CREATE EXECUTION        (CONTRACTOR-owner or ADMIN; idempotent)
    -> WORKER CHECKS IN        -> SCHEDULED -> CHECKED_IN
    -> WORKER STARTS           -> CHECKED_IN -> WORKING
    -> WORKER COMPLETES        -> WORKING -> COMPLETED
```

Dispatch answered "can we secure this worker?" (offer, acceptance, commitment). This slice answers "did
the work actually happen?" — the smallest addition that lets the system say which worker is executing
which position, whether they've checked in, and whether the work is done, without becoming a full
workforce-management system.

## Why a separate `Shift` entity, and why it stays this small

**Shift** (the name fits this codebase's own domain language — see `docs/PythonMigration.md`'s general
posture on naming — and is *not* an attempt to share a schema with the legacy TypeScript `Shift` model,
which is a much richer table with GPS check-in, wage capture, and rating linkage). It is the execution
record for exactly one COMMITTED `DispatchPosition`. `work_requirement_id`/`crew_requirement_id` are
deliberately **not** duplicated on the row — both are resolved via `dispatch_position_id ->
DispatchPosition`, which already carries them, so there's nothing to keep in sync on a second pair of
foreign keys. `worker_id` *is* stored directly (mirroring `DispatchPosition.worker_id`'s own
convention) since "who is executing this" is the record's core identity, not something worth an extra
join for every read. `scheduled_for` is a snapshot of the parent `WorkRequirement.requested_for` taken
at creation time — the same "snapshot, not re-derived on every read" convention already established by
`CrewRequirement.safety_qualification_required`.

## Hard invariant: one execution per committed position

`ShiftModel.dispatch_position_id` carries a database-level `UNIQUE` constraint
(`uq_shift_dispatch_position`) — the actual guarantee that a `DispatchPosition` can never have two
`Shift` rows, not just a service-layer check. Creation is idempotent on top of that: `ExecutionService
.create_execution` looks for an existing row first and returns it unchanged if found; if a concurrent
call still races past that check, the unique constraint rejects the second `INSERT` and the service
catches that `IntegrityError`, rolls back, and returns the (now-existing) row instead of a 500. The route
reports which case happened via status code — `201` for a genuine creation, `200` for an idempotent
return of an existing execution — rather than a separate response shape.

## Creation: cleanly separated from dispatch

`POST /api/dispatch-positions/{position_id}/execution` (CONTRACTOR-owner or ADMIN — the same ownership
check `DispatchService.dispatch` already uses, since creating an execution is an operational trigger on
the contractor's own work requirement, not a worker action):

1. The position must exist (404 otherwise).
2. The requesting contractor must own the work requirement the position belongs to, or be ADMIN (403
   otherwise).
3. If an execution already exists for this position, return it unchanged (`200`) — see "Hard invariant"
   above.
4. Otherwise the position must be `COMMITTED` with a worker attached; any other status (`OPEN`,
   `OFFERED`, `ESCALATED`, `CANCELLED`) is rejected with `409 CONFLICT` — an execution only ever
   represents work someone has actually committed to.

Execution is **never** created as a side effect of `DispatchService.accept_offer` — the two boundaries
stay separate exactly as the order asks: `DispatchPosition`'s own status is never mutated by
`ExecutionService`, and `DispatchService` never touches a `Shift` row.

## Execution state machine

```
SCHEDULED -> CHECKED_IN -> WORKING -> COMPLETED
```

Enforced by `app/services/execution_state_machine.py`, the same pattern as
`app/services/dispatch_state_machine.py`: an explicit `{status: {legal targets}}` table plus
`can_transition_shift`/`assert_shift_transition`/`is_shift_terminal`. An illegal transition raises
`AppError.invalid_state` (409) — the same shape the dispatch state machine raises, so a client sees one
consistent error vocabulary across both models. There is deliberately no `CHECKED_IN -> COMPLETED`
shortcut: nothing in this codebase's existing conventions compels one, and the order is explicit that
transitions should not be added without justification. No cancellation, abandonment, replacement,
paused, or disputed states exist in this patch — those are future layers.

The atomic *application* of a transition follows the same two-layer pattern `docs/Dispatch.md` describes
for `DispatchPosition`/`DispatchOffer`: `SqlAlchemyShiftRepository.try_transition` issues a single
`UPDATE shifts SET status = :new WHERE id = :id AND status = :expected` statement and checks
`rowcount == 1`, so a stale-state write (e.g. two calls racing to check in the same execution) is refused
at the database layer, not just by an in-Python status check.

## Worker operations

`GET /api/executions/{id}`, `POST /api/executions/{id}/check-in`, `POST /api/executions/{id}/start`,
`POST /api/executions/{id}/complete` — all WORKER-only, and all resolve **only the requesting worker's
own** execution. The ownership check lives in `ExecutionService._load_owned`, not in the route, so it
cannot be bypassed by calling the service directly — same posture as `DispatchService`'s offer-ownership
checks. There is no worker-browsing surface here: a worker can never look up another worker's execution
by id, and there is no "list all executions" endpoint.

## Attendance evidence: state and timestamps only

`check_in_at` is set (once) on the `SCHEDULED -> CHECKED_IN` transition; `completed_at` is set (once) on
the `WORKING -> COMPLETED` transition. That is the entire evidence model for this patch — no GPS, no
geofencing, no selfie or biometric verification, no fraud detection. Those are explicitly future layers,
same posture as the safety-qualification gate being "holds it or doesn't" with no expiry model.

## Scheduled time

`Shift.scheduled_for` is populated from the parent `WorkRequirement.requested_for` at creation time (see
"Why a separate Shift entity" above). No calendar system, no separate scheduling input, no editing of the
scheduled time in this patch — a `WorkRequirement` with no `requested_for` produces a `Shift` with
`scheduled_for = null`, which is a known, visible gap rather than a silently-wrong value.

## Database integrity

One new table (`shifts`), no changes to `dispatch_positions`/`dispatch_offers`/any existing table (see
the Alembic migration). `dispatch_position_id` has a `UNIQUE` constraint (the hard invariant) and a
`RESTRICT` foreign key to `dispatch_positions` (deleting a position must not silently erase its execution
history — same convention as `DispatchPosition.worker_id`'s own FK). `worker_id` is a `RESTRICT` foreign
key to `workers` for the same reason. `ix_shift_worker_status` backs a future "this worker's active
execution" lookup the same way `ix_dispatch_position_worker_status` backs the analogous dispatch-side
query.

## Concurrency

The database uniqueness constraint (not a service-layer lock) is what actually prevents two executions
for one position, and the atomic `UPDATE ... WHERE status = :expected` guard (not a service-layer check)
is what actually prevents two callers from both winning a state transition — see "Hard invariant" and
"Execution state machine" above. Neither is exercised here by a genuine concurrent-request test (unlike
`docs/Dispatch.md` TEST 8, which drives the equivalent guard directly against the atomic UPDATE) — this
patch does not claim more concurrency correctness than it actually tests. The mechanism is identical to
the one Dispatch's TEST 8 already verifies, just not re-proven with a dedicated test here, per "keep this
proportional to the patch."

## What this patch does NOT do

- No GPS, geofencing, selfie, or biometric attendance verification.
- No payroll, wage calculation, or payment of any kind.
- No attendance-fraud detection.
- No ratings or trust scoring.
- No cancellation/abandonment/replacement/paused/disputed execution states.
- No generic scheduling framework, event sourcing, CQRS, background workers, or message buses — this is
  the same request/response, service-layer-transaction architecture as the dispatch slice.
- No UI.
- No changes whatsoever to the legacy TypeScript `Job`/`JobOffer`/`Shift`/`ShiftEngine`/`DispatchEngine`,
  and no attempt to make the two implementations share a database model.
- `_utc_now()` uses the same naive-UTC workaround as `dispatch_service._utc_now` (see that module's
  docstring) — SQLite reads every `DateTime(timezone=True)` column back as tz-naive, so both sides of
  every comparison use the same naive helper. Would need revisiting on a genuinely tz-aware dialect
  (Postgres), same known limitation already flagged for the dispatch slice.
