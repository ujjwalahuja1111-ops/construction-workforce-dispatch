# Work Requirement / Crew Requirement / Dispatch Candidates

**Status:** Landed on the Python backend (`backend-py/`) as the first real slice of the redesigned
product loop: `POST`/`GET /api/work-requirements`. Nothing in the legacy TypeScript backend (`Job`,
`JobOffer`, `Shift`, `DispatchEngine`) changed — this is a new, additive capability that sits beside it,
same posture as the capability model before it (see `docs/PythonMigration.md`).

## The product loop this implements

```
CLIENT WORK REQUEST
    -> CLASSIFIED REQUIREMENT   (classification_service.classify_lines)
    -> CREW REQUIREMENT         (WorkRequirement + CrewRequirement rows)
    -> ELIGIBLE WORKERS         (matching_service.eligible_workers)
    -> CREW ASSEMBLY            (matching_service.assemble_crew)
    -> FULFILMENT STATUS        (fulfillment.line_status / overall_status)
```

A contractor (a `User` with role `CONTRACTOR` — there is no separate `Contractor` profile table on the
Python side yet, same simplification the capability API's auth already relied on) describes what work is
needed as one or more lines — task, minimum capability level, quantity, optionally an explicit
safety-qualification requirement — plus where and when. The system classifies, persists, and returns the
live-computed eligible workers, assembled crew candidates, and fulfilment status, in one response. The
contractor never browses worker profiles to get this result.

## The model

- **WorkRequirement** — the client's overall request: contractor, city/state, requested-for, notes.
- **CrewRequirement** — one line within a WorkRequirement: N workers of a given task at a minimum level,
  with a `safety_qualification_required` flag that's a *snapshot* taken at creation time (derived from
  the Task's own default unless the caller overrides it), not re-derived on every read. A single work
  requirement can hold multiple lines — "1 Mason L3+, 2 Helper L1+" for the same task is two lines, not
  one job with a headcount, which is what makes composed crews (different roles, different levels, same
  or different tasks) representable without inventing a new task per role.
- **WorkerSafetyQualification** — a worker holding a safety qualification for a specific task. Minimal by
  design: no qualification taxonomy, no expiry, no issuing body — a worker either holds the task's
  qualification or doesn't. `Task.safety_qualification_required` already existed (Patch 1) but nothing
  tracked whether a *worker* held one; this is the smallest addition that makes the gate enforceable.
- **Worker.is_available** — ported from the TS `Worker.isAvailable` field (additive column, defaults
  `True`) because matching must be able to exclude an unavailable worker and nothing on the Python side
  read or wrote this before.

## Classification: V1 and what comes after

`classification_service.classify_lines` is deterministic and structured — no AI. It validates each
requested line (level in 1–4, quantity ≥ 1, task exists and is active) and resolves the safety-
qualification default. It is a single small, swappable function specifically so a future classifier
(turning free text like "build a 1,000 sq ft brick wall" into the same `RequestedLine` shape) can replace
only this function without touching `CrewRequirement`, matching, or the API layer.

## Location matching: city only, no radius, and why

The Python `Worker` model carries `city`/`state` only — no `homeLatitude`/`homeLongitude` (those exist on
the TS `Worker` model and were never ported; see `docs/PythonMigration.md`). Matching filters on a
case-insensitive equality check against `Worker.city` when the work requirement specifies one. This is
"location/radius where existing infrastructure supports it," read literally: the infrastructure on this
side of the migration supports a city string, not a radius, so that's what's implemented — building
Haversine-based radius matching against data this backend doesn't have would mean inventing new
lat/lng-capture flows, well outside this patch's scope.

## Safety qualification gate

A line with `safety_qualification_required = true` excludes any worker without a matching
`WorkerSafetyQualification` row for that task, regardless of capability level — Test Scenario 4 verifies
this directly. There is deliberately no API to grant a qualification in this patch (the repository method
exists; nothing calls it from a route) — granting qualifications is an assessor/admin workflow, and
building that workflow wasn't asked for here. Tests seed qualifications directly via the repository, the
same pattern already used for the capability level workaround this endpoint reuses.

## Eligibility vs. assembly — and why status is based on assembled candidates, not raw eligibility

Phase E requires eligibility and ranking to stay separate concepts, and they do: `eligible_workers`
(exposed as `eligibleWorkers`/`eligibleCount` in the API) is always the full, per-line pool — task match,
level ≥ minimum, available, location, safety qualification — computed independently for each line.

But two lines can share an eligible pool. "1 Mason L3+" and "2 Helper L1+" against the *same* task means a
level-3 worker clears both lines' bars. Naively taking the top `quantity` of each line's eligible pool in
isolation would let the same worker be proposed as a candidate on two lines at once — not a real crew, since
one person cannot fill two concurrent slots on the same job. `matching_service.assemble_crew` fixes this:
it assembles candidates across *all* lines of one WorkRequirement together, processing lines
most-specialized-first (highest minimum level, ties by line order) so a harder-to-fill role gets first pick
of a shared pool, and never assigns the same worker to two lines. This is still fully deterministic — no
optimization, no scoring beyond what `eligible_workers` already established — just "don't double-book."

Because of this, `FulfillmentStatus` (`FULFILLED` / `PARTIALLY_FULFILLED` / `ESCALATED`) is computed from
the *assembled* candidate count per line, not the raw eligible count: a line can show eligible workers on
paper while having zero candidates actually left for it once a higher-priority line has claimed them, and
status has to answer "can we actually crew this," not "does anyone on paper qualify."

## Fulfilment states (Phase G)

Exactly three, computed fresh on every request (never persisted — worker availability/capability changes
between requests, and a stored snapshot would go stale):

- **FULFILLED** — every line got at least its requested quantity of assembled candidates.
- **PARTIALLY_FULFILLED** — at least one line got some, but not enough.
- **ESCALATED** — at least one line got zero.

Adjacent-capability substitution and crew substitution (tiers between an exact match and escalation) are
explicitly **not** built — `FulfillmentStatus` reserves room for them (see its docstring in
`app/domain/enums.py`) but no code path selects them today. The CTO's brief is explicit that V1 must be
deterministic and explainable, not an optimizer; adding those tiers now would be exactly the "sophisticated
optimization" it says not to build yet.

## What Phase F does NOT do

`GET`/`POST /api/work-requirements` return the correct eligible/candidate workers and a fulfilment status.
They do **not** create a `Job`, `JobOffer`, or `Shift`, and they do not notify or assign any worker.
Turning a crew-assembly result into an actual dispatch (offers, acceptance, shift creation) is exactly what
the legacy TypeScript `DispatchEngine` already does today (see `docs/DispatchEngine.md`) — duplicating that
machinery on the Python side, before this new model has been used or validated, is out of scope. This patch
stops at "here are the correct candidates," which is what Phase F explicitly asks for.

**Update:** the next patch (see `docs/Dispatch.md`) builds exactly this on top of this slice, without
changing anything described on this page. The `status` field here is unchanged; `docs/Dispatch.md` adds
a second, additive `dispatchStatus` signal instead of redefining this one. The two limitations noted
below (no persisted commitment, no cross-work-requirement awareness) are what that patch resolves.

## What the candidate view exposes, and what it doesn't

`EligibleWorkerView`/`EligibleWorkerOut` carries `workerId`, matched `level`, `provenance`, and
`city`/`state` — nothing else. No name, no phone. The product principle this patch is built around is that
"the customer should not need to understand the labour market" and should not browse worker profiles as the
primary fulfilment mechanism; a candidate list that already reads like a profile directory would work
against that principle even where it's technically just a read.

## Known limitations (not built in this patch)

- No `Contractor` profile table on the Python side — a contractor is just a `User` with role `CONTRACTOR`.
- No API to grant a `WorkerSafetyQualification` (repository method exists; no route calls it).
- No geo-radius location matching (city-string equality only — see above).
- No persisted assignment/commitment — every `GET` recomputes live; there is no "lock in this crew" action.
- No cross-work-requirement awareness — assembly dedupes workers within one WorkRequirement's lines, not
  across multiple concurrent WorkRequirements (a worker could be proposed as a candidate on two different
  work requirements at once; resolving that is a scheduling/commitment concern for whatever turns a
  candidate list into an actual dispatch, not this patch).
- `Worker.is_available` is a plain boolean, not a calendar — no notion of availability windows.
