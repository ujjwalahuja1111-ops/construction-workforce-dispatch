# Python Backend Migration

**Status:** Foundation patch landed, and the worker capability self-declaration API (`POST`/`GET
/api/worker/capabilities`) is now ported on top of it. This is still not a replacement for the
TypeScript backend yet — see "What is authoritative" below.

## Why

Product direction (2026-09-18): the long-term backend is Python (FastAPI + SQLAlchemy + Alembic,
Postgres-ready), not TypeScript. This document tracks the migration as it happens: what's authoritative,
what's legacy, what's been ported, what hasn't, and how the TypeScript backend eventually retires.

## What is authoritative right now

**Neither backend is authoritative for live traffic yet.** `backend-py/` has no mobile client pointed at
it — it exists so the next patches can build the real Python API on a real foundation, not a placeholder.
`backend/` (TypeScript) remains what the Expo app actually talks to today. Nothing about that changes in
this patch.

Once `backend-py/` has enough surface to replace a given piece of `backend/`'s API, this document will say
so explicitly, endpoint by endpoint — not as a single flag-day cutover.

## What this patch ported

Column-for-column, from `backend/prisma/schema.prisma` and `backend/src/types/domain.ts`:

- **Schema/ORM**: `Trade`, `Task`, `WorkerCapability`, `Assessment`, plus the minimal `User`/`Worker` rows
  their foreign keys require. Same field set, same `@@unique(workerId, taskId)` constraint (enforced at
  the DB layer in both), same enum *values* (`SELF_DECLARED`/`ASSESSED`/`PRACTICALLY_VERIFIED`/
  `PERFORMANCE_CONFIRMED`, `SELF_DECLARATION`/`KNOWLEDGE_TEST`/`PRACTICAL_VERIFICATION`/
  `PERFORMANCE_REVIEW`, capability levels 1–4).
- **Auth shape**: JWT claims (`sub`/`role`/`phone`), algorithm (HS256), and the `JWT_SECRET` env var name
  all match `backend/src/utils/jwt.ts`. If both services are configured with the same `JWT_SECRET` during
  the migration window, a token issued by either one verifies on the other.
- **Error shape**: `AppError` (status code, `code`, `message`, `details`) mirrors
  `backend/src/utils/errors.ts` — same status codes (400/401/403/404/409), same JSON envelope shape. A
  FastAPI/Pydantic request-validation failure (its default is HTTP 422) is now remapped to 400 by a
  `RequestValidationError` handler in `app/main.py`, so an out-of-range `level` or a malformed `taskId`
  returns the same status code the TS/Zod contract expects.
- **Clean architecture layering**: `api` (FastAPI routes) → `services` (application logic) → `domain`
  (framework-free entities/enums/view models) → `repositories` (interfaces + SQLAlchemy implementation) →
  `infrastructure` (db session, JWT). Business rules live in the service/repository layers, not in route
  handlers, matching the intent behind the TS backend's `controllers → services → prisma` split even
  though the layer names differ.
- **Worker capability self-declaration API** (`POST`/`GET /api/worker/capabilities`, `WORKER` role only):
  a port of `CapabilityService.selfDeclare`/`listForAuthenticatedWorker`
  (`backend/src/services/capability.service.ts`) and `WorkerCapabilityController`
  (`backend/src/controllers/worker-capability.controller.ts`), same three-case logic — create when no row
  exists, update the existing row in place while it's still `SELF_DECLARED`, reject with 409 once it's
  been assessed by anything else — same status codes (201/200/400/401/403/404/409), same response shape
  (`taskId`/`createdAt`/`updatedAt`/`tradeCode` on the wire via Pydantic aliases, `workerId` never
  exposed). `app/services/capability_service.py` holds the case logic; `app/domain/views.py`
  (`WorkerCapabilityView`) is the read-model the API layer shapes into JSON, populated via a
  `joinedload` on `task`/`task.trade` so the response never issues N+1 queries. Verified against all 12
  contract test cases from `patch2-contract-v2.md` §10 (`backend-py/tests/test_worker_capabilities.py`,
  ported case-for-case from `backend/tests/worker-capability.test.ts`).

## What has deliberately NOT been ported (yet)

Everything not listed above, specifically including: `Job`/`JobOffer`/`Shift`/`ShiftEvent`, `Rating`,
`Notification`, `Otp`, `Worker`'s counters (`trustScore`, `avgRating`, `totalShifts`, `cancelledShifts`,
...), `DispatchEngine`, `ShiftEngine`, `TrustEngine`, and the phone+OTP request/verify flow (auth
*verification* is ported; auth *issuance* is not — see "Retirement plan" below). This patch adds the
first real write-side business logic on top of the foundation patch; everything else in this list remains
future work, one vertical slice at a time.

`Worker.skills` (the legacy flat-skill CSV) is carried over as an unused, deprecated column
(`workers.skills_csv`) purely so a `Worker` row created here stays shape-compatible with its TS
counterpart during the transition — nothing in the Python service reads or writes it, and it is not the
foundation for anything new.

There is no taxonomy seed script or admin endpoint on the Python side yet — the frozen V1 taxonomy (3
trades / 11 tasks, identical to `backend/prisma/seeds/taxonomy.ts`) exists only as test fixtures
(`backend-py/tests/factories.py`) until a real seeding need (e.g. a `GET /api/taxonomy` endpoint) makes it
worth adding as production code.

## Retirement plan for the TypeScript backend

Not scheduled yet — retiring `backend/` is a product decision, not an engineering one, and depends on
`backend-py/` reaching feature parity with what the mobile app actually calls today. The intended shape of
that transition:

1. ~~Port capability write endpoints (self-declaration) onto this foundation~~ — done, this patch.
2. Port auth issuance (phone + OTP) so `backend-py/` can issue its own tokens, not just verify tokens
   issued elsewhere.
3. Port the remaining worker-facing surface (profile, location, availability, offers, shifts, earnings)
   incrementally, each patch swapping one vertical slice, each verified against the same contract-style
   review this project already uses for TS patches.
4. Only once the mobile app is pointed at `backend-py/` for a given surface does `backend/`'s equivalent
   route become legacy-only; it is not deleted until nothing calls it.
5. `backend/` is deleted only after every surface has moved and a deprecation window has passed — not as
   part of any single patch.

Until step 4 starts for a given surface, treat `backend/` as the source of truth for that surface's
business rules, and `backend-py/` as reference/migration material moving in the opposite direction from
how this document opens — i.e., during the build-out of a not-yet-ported surface, `backend/`'s existing
implementation is what a new `backend-py/` patch should read to preserve semantics, exactly as this
foundation patch read `prisma/schema.prisma` and `domain.ts` rather than inventing new shapes.

## Running it locally

```
cd dispatch-platform/backend-py
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env               # sqlite by default; point DATABASE_URL at Postgres when ready
alembic upgrade head
uvicorn app.main:app --reload --port 8003
```

Tests never touch `dev.db` — `tests/conftest.py` builds an isolated in-memory SQLite database per test via
`Base.metadata.create_all`, not Alembic, and overrides FastAPI's `get_db`/`get_settings` dependencies.

```
pytest
ruff check .
mypy app
```
