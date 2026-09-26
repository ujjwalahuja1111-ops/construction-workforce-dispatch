# Dispatch Position / Dispatch Offer / Commitment

**Status:** Landed on the Python backend (`backend-py/`) as the second real slice of the redesigned
product loop: `POST /api/work-requirements/{id}/dispatch`, `POST /api/dispatch/offers/{id}/accept`,
`POST /api/dispatch/offers/{id}/decline`, `POST /api/dispatch/offers/expire`. Builds directly on
`docs/WorkRequirement.md`'s WorkRequirement/CrewRequirement/matching slice — nothing there was redone,
only extended. Nothing in the legacy TypeScript backend (`Job`, `JobOffer`, `Shift`, `DispatchEngine`)
changed.

## The product loop this adds

```
ELIGIBLE WORKERS (matching_service, unchanged, reused)
    -> DISPATCH POSITION       (one per unit of CrewRequirement.quantity)
    -> DISPATCH OFFER          (one position, one worker, PENDING)
    -> WORKER ACCEPTS          -> position COMMITTED, offer ACCEPTED,
                                   competing offers on the same position CANCELLED
    -> WORKER DECLINES         -> offer DECLINED, position reopens (unless
                                   already committed by a different offer)
    -> OFFER EXPIRES           -> same reopening, system-driven instead of worker-driven
    -> REDISPATCH               -> the reopened position is dispatched again,
                                   excluding whoever already declined/expired for
                                   THIS position
```

Phase F answered "who could perform this work?" (candidate discovery). This slice answers "can we
actually secure those workers?" (offer, acceptance, commitment). The system controls fulfilment — a
contractor calls `dispatch`, never browses and hand-picks a worker.

## Why two new concepts, not more

**DispatchPosition** — each unit of a CrewRequirement's `quantity` is one independently fulfillable
position ("1 Mason L3+" is one position; "2 Helper L1+" is two). A position is created once, at
WorkRequirement-creation time (`WorkRequirementService.create`), not invented lazily at first dispatch —
"the position is the unit that gets fulfilled" exists from the moment the requirement does.
`position_index` (0-based, unique within its CrewRequirement) is the position's stable identity,
independent of its lifecycle state.

**DispatchOffer** — one position, one worker, with a small, closed status set (PENDING / ACCEPTED /
DECLINED / EXPIRED / CANCELLED), all reachable directly from PENDING. No ranking/scoring fields, no
notification model, no audit-event table — the TS `ShiftEvent` audit-trail pattern was deliberately not
ported; a `DispatchOffer` row's own `status`/`responded_at` already is the audit trail for what happened
to it, and adding a second event-log table for the same fact would be exactly the "unnecessary
abstraction" the order says not to build.

## Position state machine

```
OPEN -> OFFERED -> COMMITTED
```

plus the explicit failure/recovery transitions:

- `OFFERED -> OPEN` (decline or expiry reopens the position)
- `OFFERED -> CANCELLED`
- `OPEN -> ESCALATED`, `ESCALATED -> OFFERED` (a dispatch attempt that finds zero valid candidates
  marks the position ESCALATED — an explicit "cannot currently be filled" signal, never a silent OPEN
  left with no visible reason; the next dispatch call reconsiders it, so it is not a dead end)
- `COMMITTED -> OPEN` — reachable ONLY through an explicit replacement/re-dispatch operation. No route
  exposes a generic "set position status" endpoint; the only code path that ever requests this
  transition today would be a future explicit replacement operation, which this patch does not add (see
  "Known limitations").

Enforced by `app/services/dispatch_state_machine.py`, mirroring the legacy TypeScript `ShiftEngine`'s
pattern almost exactly: an explicit `{status: {legal targets}}` table plus `can_transition_position` /
`assert_position_transition` / `is_position_terminal`. An illegal transition raises
`AppError.invalid_state` (409), the new classmethod added to mirror TS's `AppError.invalidState`. The
same pattern is used for `DispatchOffer` (`OFFER_TRANSITIONS`) even though every offer transition
terminates at PENDING's targets, for consistency and because "test invalid transitions" applies to both
state models, not just positions.

### Two-layer transition safety

The state-machine table above answers "is this transition legal at all" using the status this service
just read — which can be stale under concurrency. The actual concurrency guard is one layer lower, in
the repository: `SqlAlchemyDispatchPositionRepository.try_transition` (and the offer equivalent) issue a
single `UPDATE dispatch_positions SET status = :new WHERE id = :id AND status = :expected` statement and
check `rowcount == 1`. Whichever concurrent caller's UPDATE the database applies first wins; the loser's
statement matches zero rows once the winner's write lands — one atomic SQL statement, no window for two
callers to both "win," regardless of how many application-server processes or threads race for it. This
is the mechanism TEST 8 (the double-accept race) verifies.

## Dispatch endpoint

`POST /api/work-requirements/{id}/dispatch` (CONTRACTOR-owner or ADMIN):

1. Load the WorkRequirement, check ownership (same pattern as `GET`).
2. List every position for it; process those not COMMITTED/OFFERED/CANCELLED — i.e. OPEN or ESCALATED —
   most-specialized-first (highest `min_level`, same priority order `matching_service.assemble_crew`
   already uses), so a harder-to-fill role gets first pick of a shared eligible pool.
3. For each such position, call the **existing** `matching_service.eligible_workers` — never
   reimplemented, never bypassed — then narrow it with dispatch-specific exclusions:
   - workers who already declined/expired for **this exact position** (never re-offered here, though
     they remain eligible for a different position on the same or another line),
   - workers holding a live (PENDING, unexpired) offer anywhere in **this** WorkRequirement (point 7 —
     never offered twice within one requirement),
   - workers COMMITTED to any position in this WorkRequirement,
   - and, when `requested_for` is set, workers COMMITTED or holding a live offer on a
     **conflicting-date** WorkRequirement elsewhere (see "Cross-work-requirement conflicts" below).
4. The first remaining candidate (deterministic order, unchanged from Phase E) gets a new
   `DispatchOffer` (PENDING, `expires_at = now + dispatch_offer_ttl_minutes`); the position moves
   OPEN/ESCALATED -> OFFERED. If none remain, the position moves to ESCALATED (a no-op if it already
   was).
5. Returns a `DispatchSummaryView`: per-position outcome (status, the offer if one was just created or
   is already live) plus aggregate counts — never a worker-browsing candidate list.

Each position's transition is applied (and, for a new offer, flushed) before the next position in the
same call is considered, so a worker just offered position 1 of this WorkRequirement is correctly
excluded from position 2 of the same call — no separate "already assigned this call" bookkeeping needed
beyond what's already persisted.

## Offer acceptance

`POST /api/dispatch/offers/{id}/accept` (WORKER, must own the offer) — one transaction
(`DispatchService.accept_offer`, single `db.commit()` at the end, nothing partially applied on any
failure path):

1. Resolve the worker from the token; 403 if the offer belongs to someone else.
2. 409 unless the offer is PENDING.
3. Lazily expire it (see "Expiry") and 409 if `expires_at` has passed.
4. 409 unless the position is still OFFERED.
5. Re-check the hard capability level, `Worker.is_available`, the safety qualification if the line
   requires one, and the cross-work-requirement date conflict — all fresh, none trusted from
   dispatch-time.
6. Atomically flip the position OFFERED -> COMMITTED via the guarded `try_transition` (see "Two-layer
   transition safety") — a 409 here means someone else's acceptance won the race.
7. Flip this offer PENDING -> ACCEPTED, then cancel every other PENDING offer on the same position
   (TEST 9) — all before the single commit, so no reader ever observes a COMMITTED position with a
   still-PENDING competing offer.
8. Recompute the WorkRequirement's `dispatch_status` (see "Fulfilment semantics") and return the
   committed assignment.

"Impossible states impossible": an accepted offer with an uncommitted position, or two workers committed
to one position, would both require either step 6's guarded UPDATE to apply twice for one position
(impossible — a single `UPDATE ... WHERE status = 'OFFERED'` can only ever flip a row once) or step 6 to
succeed while step 7 is skipped (impossible — both happen before the one commit, and any exception
between them rolls back the whole transaction via `get_db`'s rollback-on-exception).

## Decline

`POST /api/dispatch/offers/{id}/decline` (WORKER, must own the offer): 409 unless PENDING; on success,
offer -> DECLINED and, only if the position is still OFFERED (i.e. no other offer already committed it
first), position -> OPEN. "Do not silently escalate if valid candidates remain" — decline never
escalates by itself; escalation only happens inside `dispatch()` when a redispatch attempt genuinely
finds no candidate.

## Expiry

No background scheduler exists on either backend today (confirmed by inspecting the legacy TS
`DispatchEngine` — offers there sit PENDING past their TTL and are only lazily filtered, never
proactively expired) — this patch doesn't add one either, per the order's explicit instruction. Instead:

- **Lazy expiry**: `accept_offer` checks `expires_at` itself and expires-in-place before rejecting, so an
  expired offer is never silently treated as acceptable just because nothing had processed it yet.
- **Explicit processing**: `POST /api/dispatch/offers/expire` (ADMIN) — an internal/operational trigger
  that finds every PENDING offer past its TTL, expires it, and reopens its position. A cron, ops script,
  or future scheduler can call this; this patch only provides the deterministic operation itself.

TTL is `Settings.dispatch_offer_ttl_minutes` (default 15, matching the legacy TS DispatchEngine's
15-minute default), configurable via `DISPATCH_OFFER_TTL_MINUTES` — not hard-coded.

## Redispatch

Both decline and expiry reopen a position to OPEN, and the very next `dispatch()` call reconsiders it
using the same eligibility + exclusion pipeline as a first dispatch — no separate "redispatch" code path
exists, because none is needed: redispatch **is** dispatch, called again, with the one addition that a
worker who already declined/expired for that specific position is excluded from being re-offered it
(the same worker remains eligible for a *different* position). TEST 3 and TEST 4 demonstrate this for
decline and expiry respectively; TEST 10 demonstrates the terminal case where redispatch finds nobody
left.

## Cross-work-requirement conflicts: the V1 rule

The previous patch only deduplicated a worker across lines of **one** WorkRequirement. This patch adds a
cross-requirement rule, explicitly scoped down per the order ("do NOT build a full availability calendar
yet"):

> Two WorkRequirements conflict when **both** have a non-null `requested_for` and those two timestamps
> fall on the **same calendar date** (UTC date component). A worker COMMITTED to a position, or holding
> a live PENDING/unexpired offer, on a WorkRequirement with a conflicting date is excluded from
> candidacy on the other WorkRequirement's dispatch — both at dispatch time (`_pick_candidate`) and
> re-checked at accept time (a worker could commit elsewhere between offer and acceptance).

What this deliberately does **not** do: reason about time-of-day overlap (a 9am job and a 2pm job on the
same date conflict under this rule even though a real person could physically do both), reason about
undated WorkRequirements at all (no `requested_for` means this rule never fires for that requirement —
a known gap, not a silent bug), or build any notion of a worker's calendar, shift length, or travel time.
This is intentionally the smallest rule that uses "current WorkRequirement scheduling information"
(`requested_for`) as asked, not a scheduling engine.

## Fulfilment semantics: two signals, not one

The previous patch's `status` (`WorkRequirementResultView.status` / `CrewRequirementResultView.status`)
is **candidate-assembly** based — "could this plausibly be crewed given who's currently eligible" — and
is **unchanged** by this patch: computed exactly as `docs/WorkRequirement.md` describes, and every one of
the 22 existing Phase F/G tests still passes unmodified against it.

This patch adds a second, additive field — `dispatch_status` (`dispatchStatus` on the wire), at both the
WorkRequirement and CrewRequirement level, alongside new operational counts
(`requiredPositions`/`committedPositions`/`openPositions`/`escalatedPositions`/`pendingOffers`) — driven
by **actual DispatchPosition commitment**, never candidate counts: "CANDIDATES ≠ COMMITTED WORKERS." Per
line (`fulfillment.dispatch_line_status`):

- **FULFILLED** — every position for the line is COMMITTED.
- **ESCALATED** — at least one position for the line is itself ESCALATED (exhausted every valid
  candidate) — "no viable path for a required position," regardless of how many other positions on the
  same line are already committed.
- **PARTIALLY_FULFILLED** — anything else: some committed, some still open/offered and not (yet)
  escalated. This deliberately covers "not yet dispatched at all" as well as "dispatch in progress" —
  neither is a failure, so neither is ESCALATED; "unresolved" is the accurate word for both.

The WorkRequirement-level `dispatch_status` aggregates line-level `dispatch_status` values with the same
rule Phase G already established for `status` (`fulfillment.overall_status`, reused unchanged): any
ESCALATED line makes the whole requirement ESCALATED; otherwise any PARTIALLY_FULFILLED line makes it
PARTIALLY_FULFILLED; otherwise FULFILLED.

**Why additive, not in-place redefinition:** the order's fulfilment section reads naturally as "the
dispatch flow's own fulfilment concept must be commitment-based," and the *existing*, already-shipped,
already-tested `status` field answers a genuinely different, still-useful question (Phase F's "is this
requirement staffable at all, right now, on paper"). Redefining `status` in place would have silently
broken all 22 of Patch 1's test assertions (which check `status == "FULFILLED"` immediately after
creation, before any dispatch call — correct under the candidate-assembly reading, wrong under a
commitment reading) for a change the order does not explicitly demand in those words. Keeping both is
also what "do not remove useful candidate information" most straightforwardly means in this context: the
old signal stays exactly as useful as it was, and the new one answers the new question the order actually
poses. If a future patch wants `status` itself redefined in place, that's an explicit, visible decision
for that patch to make and to update Patch 1's tests to match — not an implicit side effect of this one.

## Database integrity

Two new tables, no changes to `work_requirements`/`crew_requirements`/existing tables (see the Alembic
migration). Constraints/indexes, one per the order's explicit list:

- **Position identity** — `dispatch_positions.id` (primary key) plus
  `UNIQUE(crew_requirement_id, position_index)`, so a position has a stable identity distinct from its
  mutable `status`.
- **One committed worker per position** — a `CHECK` constraint:
  `(status = 'COMMITTED' AND worker_id IS NOT NULL) OR (status != 'COMMITTED' AND worker_id IS NULL)`.
  Since `worker_id` is a single column, a position can never reference two workers at once by
  construction; the check constraint additionally makes "worker reference without COMMITTED" and
  "COMMITTED without a worker reference" both impossible at the database layer, not just by service-layer
  discipline.
- **Duplicate offer prevention** — a partial unique index on `dispatch_offers(position_id, worker_id)`
  `WHERE status = 'PENDING'`: at most one live offer per (position, worker) pair; a worker who declined
  or expired can be offered the same position again later (a new row), but never holds two live offers
  for it simultaneously.
- **Worker active commitment lookup** — `ix_dispatch_position_worker_status` on
  `(worker_id, status)`, backing "is this worker committed to any active position" (used by the conflict
  checks).
- **Pending offer lookup** — `ix_dispatch_offer_worker_status` on `(worker_id, status)` and
  `ix_dispatch_offer_position_status` on `(position_id, status)`.
- **Expiry lookup** — `ix_dispatch_offer_status_expires` on `(status, expires_at)`, backing
  `list_expired_pending`.

All of the above are backed by the transactional domain validation described earlier (the state machine
plus the guarded atomic updates) — the constraints are a backstop against a bug or a future caller that
skips the service layer, not a substitute for it.

## Shift boundary

Unchanged from the existing plan: this patch ends at COMMITTED. `DispatchService` is the clean service
boundary the next integration into Shift/Execution will sit behind — nothing about the legacy TypeScript
`ShiftEngine`/`ShiftService` was touched or duplicated.

## Authorization

- **Worker**: accept/decline only their own offer (`DispatchOffer.worker_id` resolved from the
  authenticated user's `Worker` row, checked before any mutation — enforced in `DispatchService`, so it
  cannot be bypassed by calling the service directly). A dedicated "list my offers" read endpoint was not
  part of the 10 mandated tests and is not included in this patch — see "Known limitations."
- **Contractor**: dispatch and inspect only their own WorkRequirements — the same ownership check
  `WorkRequirementService.get` already used, reused verbatim in `DispatchService.dispatch`.
- **Admin**: existing admin bypass rules (`Role.ADMIN` may dispatch/inspect any WorkRequirement, same as
  Phase F); the expiry-processing endpoint is ADMIN-only as an internal operational trigger.

## What this patch does NOT do

- No background scheduler (explicitly out of scope; see "Expiry").
- No `Contractor`-owned "replace a committed worker" operation — the COMMITTED -> OPEN transition exists
  in the state machine (a future patch needs it), but nothing in this patch calls it; a committed
  position can only be reopened today via decline/expiry on a *pending* offer, never on an already-
  COMMITTED one.
- No "list my offers" read endpoint for a worker (see "Authorization").
- No full availability calendar (see "Cross-work-requirement conflicts").
- No ML/AI ranking, trust scoring, or distance-based candidate ordering — offers still go out in the
  exact deterministic order `matching_service.eligible_workers` already established.
- No changes whatsoever to the legacy TypeScript `Job`/`JobOffer`/`Shift`/`DispatchEngine`/`ShiftEngine`.
- Datetime comparisons in the expiry/conflict logic are done as naive UTC
  (`dispatch_service._utc_now`), because SQLite (the only dialect this test suite exercises) reads back
  every `DateTime(timezone=True)` column as tz-naive regardless of what was written — comparing that
  against an aware "now" raises `TypeError`. Verified correct against SQLite; would need revisiting
  (e.g. a `TypeDecorator` or explicit UTC session normalization) if/when this backend moves to Postgres,
  the stated eventual target per `docs/PythonMigration.md`.
