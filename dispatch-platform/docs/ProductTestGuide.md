# Product Test Guide — running the core journey today

**Status:** Added for the "test the product today" sprint. This document does not describe a new
product capability — it's the shortest path from a clean checkout of `backend-py/` to actually executing
the core journey:

```
CONTRACTOR -> LOGIN -> CREATE WORK -> CLASSIFY -> DISPATCH
    -> WORKER -> LOGIN -> SEE OWN OFFER -> ACCEPT
    -> CONTRACTOR -> CREATE EXECUTION
    -> WORKER -> CHECK IN -> START -> COMPLETE
```

against `backend-py` alone, using only what already exists in this repository (plus the two small,
minimal additions this sprint made — see "What this sprint added" below).

## Why not the existing mobile app

`mobile/` (a symlink to a sibling Expo app) is a worker-only client that talks exclusively to the
**legacy TypeScript backend** on port 8002 (`src/api/client.ts`'s `EXPO_PUBLIC_BACKEND_URL`), using that
backend's phone+OTP login and its `Job`/`JobOffer`/`Shift` model (`/worker/offers`, `/jobs/offers/accept`,
`/shifts/:id/:action`). There is no contractor-facing client at all (Phase 2 of `docs/Roadmap.md`,
the contractor web portal, was never built). Pointing that app at `backend-py` would mean replacing its
entire auth flow and its entire API client, not "a small amount of work" — so per this sprint's explicit
instruction, it was **not** touched. This guide is the lightweight developer/test harness used instead:
curl (or Postman/HTTPie) directly against `backend-py`'s own HTTP API, which already exposes interactive
API docs at `/docs` (Swagger UI, FastAPI's default — nothing had to be added for that).

## What this sprint added (and why)

- **`GET /api/dispatch/offers`** — a worker previously had `accept`/`decline` endpoints but no way to
  *discover* a pending offer's id in the first place. This is the minimal read that closes that gap: it
  resolves the worker from the JWT and returns only that worker's own offers (any status), with enough
  task/position/work-requirement context to understand and act on the work. No worker-browsing, no other
  worker's data — see `docs/Dispatch.md`.
- **`scripts/dev_seed.py`** — `backend-py` has no phone+OTP login endpoint of its own yet (auth
  *verification* is ported, auth *issuance* is not — see `docs/PythonMigration.md`), so there was
  previously no way to obtain a bearer token against a live server at all outside the test suite. This
  script is a dev-only tool, not a second auth system: it seeds one deterministic contractor, one worker
  (with a Level-3 `BRICKWORK_NEW_WALL` capability), and the one trade/task those need, then mints tokens
  for both through the exact same `create_access_token` function the app already verifies against. It
  introduces no new HTTP endpoint and is idempotent — safe to re-run.

Neither addition changes any existing domain contract: dispatch is still blind, eligibility is still
capability/task/location/availability/safety based, `DispatchPosition`/`DispatchOffer`/`Shift` and their
state machines are all unchanged.

## Running the journey

```bash
cd dispatch-platform/backend-py
source .venv/bin/activate
cp .env.example .env               # sqlite by default
alembic upgrade head
python -m scripts.dev_seed
```

This prints `CONTRACTOR_TOKEN`, `WORKER_TOKEN`, and `TASK_ID`. Export them, then start the server in
another terminal (`uvicorn app.main:app --reload --port 8003`):

```bash
export CONTRACTOR_TOKEN=...   # from the seed output
export WORKER_TOKEN=...
export TASK_ID=...

# 1. CREATE WORK REQUIREMENT (classification + CrewRequirement happen inside this call)
curl -s -X POST http://localhost:8003/api/work-requirements \
  -H "Authorization: Bearer $CONTRACTOR_TOKEN" -H "Content-Type: application/json" \
  -d "{\"city\":\"Bengaluru\",\"state\":\"Karnataka\",\"requestedFor\":\"2026-10-12T09:00:00Z\",\"lines\":[{\"taskId\":\"$TASK_ID\",\"minLevel\":3,\"quantity\":1}]}" | tee /tmp/wr.json
WR_ID=$(python3 -c "import json;print(json.load(open('/tmp/wr.json'))['id'])")

# 2. DISPATCH
curl -s -X POST http://localhost:8003/api/work-requirements/$WR_ID/dispatch \
  -H "Authorization: Bearer $CONTRACTOR_TOKEN" | tee /tmp/dispatch.json
POSITION_ID=$(python3 -c "import json;print(json.load(open('/tmp/dispatch.json'))['positions'][0]['positionId'])")

# 3. WORKER SEES OWN OFFER
curl -s http://localhost:8003/api/dispatch/offers -H "Authorization: Bearer $WORKER_TOKEN" | tee /tmp/offers.json
OFFER_ID=$(python3 -c "import json;print(json.load(open('/tmp/offers.json'))[0]['id'])")

# 4. WORKER ACCEPTS
curl -s -X POST http://localhost:8003/api/dispatch/offers/$OFFER_ID/accept -H "Authorization: Bearer $WORKER_TOKEN"

# 5. CONTRACTOR CREATES EXECUTION
curl -s -X POST http://localhost:8003/api/dispatch-positions/$POSITION_ID/execution \
  -H "Authorization: Bearer $CONTRACTOR_TOKEN" | tee /tmp/execution.json
EXECUTION_ID=$(python3 -c "import json;print(json.load(open('/tmp/execution.json'))['id'])")

# 6. WORKER CHECKS IN, STARTS, COMPLETES
curl -s -X POST http://localhost:8003/api/executions/$EXECUTION_ID/check-in -H "Authorization: Bearer $WORKER_TOKEN"
curl -s -X POST http://localhost:8003/api/executions/$EXECUTION_ID/start    -H "Authorization: Bearer $WORKER_TOKEN"
curl -s -X POST http://localhost:8003/api/executions/$EXECUTION_ID/complete -H "Authorization: Bearer $WORKER_TOKEN"
```

The final `complete` response's `status` is `COMPLETED`, with both `checkInAt` and `completedAt` set —
the Definition of Done: `DispatchPosition = COMMITTED`, `DispatchOffer = ACCEPTED`,
`Shift/Execution = COMPLETED`.

## Automated coverage of the same journey

`tests/test_journey.py::test_complete_product_journey_contractor_to_completed_execution` runs exactly
this flow through the real HTTP/service boundary (FastAPI's `TestClient`, not a unit-test simulation of
internal methods) and asserts the persisted ORM row state — not just the HTTP response body — after every
transition. Run it on its own with `pytest tests/test_journey.py -v`, or as part of the full suite.

## Failure/recovery paths

These were exercised (and pass) before this sprint and remain unchanged; this sprint only re-verified
them, per its explicit "do not invent new failure-state architecture" instruction:

| Scenario | Existing test |
| --- | --- |
| Worker declines offer, position redispatches | `test_dispatch.py::test_3_decline_then_redispatch_offers_replacement` |
| Offer expires, position redispatches | `test_dispatch.py::test_4_expiry_then_redispatch_offers_another_candidate` |
| No eligible worker -> explicit escalation | `test_dispatch.py::test_5_capability_gate_excludes_below_minimum_worker`, `test_10_exhaustion_escalates_explicitly` |
| Wrong worker attempts to accept another's offer | `test_dispatch.py::test_accept_forbidden_for_non_owning_worker` |
| Duplicate acceptance of the same offer | `test_dispatch.py::test_double_accept_same_offer_is_rejected` |
| Duplicate execution creation (idempotent, and DB-enforced) | `test_execution.py::test_repeated_creation_is_idempotent`, `test_database_prevents_duplicate_execution` |
| Wrong worker attempts an execution action | `test_execution.py::test_worker_cannot_mutate_another_workers_execution` |
| Worker already committed elsewhere (cross-work-requirement conflict) | `test_dispatch.py::test_7_cross_work_requirement_conflict_excludes_committed_worker` |

## Known limitations of this test harness

- No real phone+OTP login exists in `backend-py` yet — "login" in this guide means minting a token via
  `scripts/dev_seed.py` (dev/test-only, refuses to run when `NODE_ENV=production`). Building real auth
  issuance is out of this sprint's scope (see `docs/PythonMigration.md` "Retirement plan" step 2).
- `scripts/dev_seed.py` seeds exactly one trade/task/contractor/worker — enough for the happy path, not a
  general-purpose fixture generator.
- No UI was built or connected; this is command-line/API-level testing only, as the sprint's scope
  required.
