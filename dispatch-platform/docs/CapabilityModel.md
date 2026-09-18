# Capability Model — Trade / Task / WorkerCapability / Assessment

**Status:** Patch 1 (Milestone 0C) landed the schema, seed data, and a
minimal service layer. **Patch 2 has now landed on top of it**: worker
self-declaration is live at `POST`/`GET /api/worker/capabilities` (see
`worker-capability.controller.ts`, `CapabilityService.selfDeclare`, and the
approved contract, `patch2-contract-v2.md`, for the full request/response
shape and the three-case duplicate/update/reject semantics). `assessment`,
`ASSESSED`/`PRACTICALLY_VERIFIED`/`PERFORMANCE_CONFIRMED` provenance, and
any assessor-facing (contractor/admin) write path are still **not** exposed
by any API — this patch only ever writes `SELF_DECLARED`. **Nothing in
dispatch reads this graph yet** — `DispatchEngine` still matches purely on
the legacy `Worker.skills` CSV vs. `Job.skill`, exactly as before this
patch. This document is the spec for the model that landed, not a promise
about when dispatch starts consuming it.

---

## 1. Why a second system exists

The legacy skill model is a flat CSV on `Worker.skills` (`"MASON,HELPER"`)
matched against a single `Job.skill` string. It has no notion of skill
*level*, no evidence trail, and no way to represent "can do brickwork
independently but is only assist-level on plastering." `KnownLimitations.md`
§3.1 already flagged the CSV-string design as something to outgrow past
~30 skills or once per-skill certification metadata is needed — this patch
is the first step of that, scoped narrowly to persistence only.

**The two systems run side by side on purpose during migration:**

| | Legacy | New |
|---|---|---|
| Where | `Worker.skills` (CSV string), `Job.skill` (single string) | `Trade` → `Task` → `WorkerCapability` → `Assessment` |
| Granularity | One flat skill code | A specific task, with a 1–4 level and provenance |
| Read by dispatch today | **Yes** — `DispatchEngine` | **No** |
| Mutated by this patch | **Not touched** | New tables only |

Nothing automatically populates `WorkerCapability` from `Worker.skills`, and
nothing writes back the other way. That's deliberate (Contract §12) — a
migration/backfill strategy from the legacy CSV into real `WorkerCapability`
rows is future work, not assumed here.

---

## 2. The graph

```
Trade
  └── Task
        ├── WorkerCapability
        │      └── Assessment
        └── (future) CrewSlot / PerformanceRecord — not built in this patch

Worker
  └── WorkerCapability
```

- **Trade** — a normalized reference entity (`MASONRY`, `ELECTRICAL`,
  `PLUMBING`). No skill level, no worker data, no dispatch logic lives here.
  Deactivate (`isActive = false`) rather than delete; the DB enforces this
  at the FK level too — a `Trade` with `Task`s under it cannot be deleted
  (`onDelete: Restrict`), only deactivated.
- **Task** — the atomic unit for capability and (eventually) dispatch, e.g.
  `BRICKWORK_NEW_WALL`. Same deactivate-don't-delete rule, same DB-level
  `Restrict` enforcement once a `WorkerCapability` references it.
  `adjacencyGroup` is a reserved, currently-inert column for a future
  dispatch-fallback grouping (e.g., "someone capable at BLOCKWORK can also
  be offered BRICKWORK_REPAIR at a lower priority") — it activates no
  behaviour in this patch.
- **WorkerCapability** — one row per (worker, task) pair: what level, from
  what provenance. `@@unique(workerId, taskId)` — a worker has at most one
  capability record per task (updating it, not adding a second row, is how
  a level changes over time — that update path isn't built yet either;
  today the service layer only creates).
- **Assessment** — append-only evidence backing a `WorkerCapability`: what
  kind of check happened, what the outcome was, who ran it, when.

---

## 3. Level semantics (frozen in Patch 0C)

Stored as a plain `Int` (1–4) on `WorkerCapability.level`. These are
**capability levels, not job titles**, and are **never trade-specific** —
level 3 in `PLASTER` means the same thing as level 3 in `WIRING`.

| Level | Meaning |
|---|---|
| L1 | Assist / Directed |
| L2 | Independent, standard work |
| L3 | Independent + basic troubleshooting |
| L4 | Expert / complex & novel |

The numeric value is the source of truth in the DB; the semantic labels
live in code as `CapabilityLevelDescription` (`src/types/domain.ts`), not
duplicated as a second column.

---

## 4. Provenance semantics

`WorkerCapability.provenance` is one of four states, describing *how* a
level was established — not a maturity ladder the system enforces:

- `SELF_DECLARED` — the worker says so.
- `ASSESSED` — someone ran a formal assessment (knowledge test, etc.).
- `PRACTICALLY_VERIFIED` — verified via a hands-on practical check.
- `PERFORMANCE_CONFIRMED` — confirmed by actual on-the-job performance.

**No one-way progression is enforced at the database level.** A worker's
provenance can move in either direction (a `PERFORMANCE_CONFIRMED` level
could later be downgraded after a bad outcome) — Patch 1 only stores the
current state; progression/downgrade *logic* is future work, not built
here.

---

## 5. Assessment types

`Assessment.type` is one of `SELF_DECLARATION`, `KNOWLEDGE_TEST`,
`PRACTICAL_VERIFICATION`, `PERFORMANCE_REVIEW`. `Assessment` rows are
**append-only evidence** — `AssessmentService` (`src/services/
assessment.service.ts`) exposes `record()` and `listForCapability()` only;
there is no `update`/`delete` method, and no DB-level immutability trigger
was added (see "architectural decisions" below for why).

---

## 6. `confidence`, `restrictions`, `evidenceRef` — reserved, not implemented

Three columns on `WorkerCapability` are intentionally inert in this patch:

- **`confidence`** (`Float?`) — reserved for a future confidence score.
  **No formula is defined.** It is not calculated from experience, from
  `Worker.trustScore`, or from anything else, and it is not read by
  dispatch. It is `null` on every row created by this patch's service layer
  unless a caller explicitly supplies a value.
- **`restrictions`** (`String?`) — reserved for future structured
  restrictions (e.g., "supervised only," "daylight hours only"). Stored as
  an opaque string for now rather than a JSON schema or a separate table —
  deliberately the simplest representation that doesn't foreclose a real
  structure later.
- **`evidenceRef`** (`String?`) — reserved for a future pointer to stored
  evidence (a photo, a document, a test result). Opaque string for now, no
  evidence storage system built.

---

## 7. V1 taxonomy

Seeded by `prisma/seeds/taxonomy.ts` (idempotent — upserts on `code`, never
on name; safe to run standalone via `npm run seed:taxonomy` or as part of
`npm run seed`).

| Trade | Tasks |
|---|---|
| `MASONRY` | `BRICKWORK_NEW_WALL`, `BRICKWORK_REPAIR`, `BLOCKWORK`, `PLASTER` |
| `ELECTRICAL` | `FAN_INSTALLATION`, `LIGHT_INSTALLATION`, `WIRING`, `FAULT_FINDING` |
| `PLUMBING` | `LEAKAGE_REPAIR`, `PIPE_INSTALLATION`, `BATHROOM_PLUMBING` |

**Resolved by CTO review (Patch 1 approval):** the approved V1 taxonomy is
**3 Trades, 11 Tasks** (4 + 4 + 3), exactly as named above. The "12 Tasks"
wording that appeared in the patch's own earlier scope-document section
headers was a documentation error, not an omitted task — the authoritative
seed list is these 11 explicitly named tasks, and no 12th task was invented
to force the count.

Do not expand this list without a scoped follow-up patch.

---

## 8. Why enums are plain `String` columns here too

**Database constraints protect structural integrity and relationships.
Domain-value validation for capability level, provenance and assessment
type is enforced in the service/domain layer.** This is intentional and
consistent with the current architecture, confirmed on CTO review of
Patch 1.

Concretely: `level`, `provenance`, and `Assessment.type` are validated in
`CapabilityService`/`AssessmentService` (Zod), not as a DB `CHECK`
constraint or a Prisma `enum`. This matches every other enum-like column
already in this schema (`Job.status`, `Shift.state`, `JobOffer.status`,
`Rating.score` — see `KnownLimitations.md` F2): the codebase's existing,
accepted convention is app-layer validation on `String` columns, and
introducing the first DB-level enum specifically for this patch would be an
inconsistency the patch wasn't scoped to fix. The database instead carries
the load of structural integrity — foreign keys, `@@unique(workerId,
taskId)`, and `Restrict`-on-delete for referenced Trades/Tasks, all
verified directly in §3/§7 of the Patch 1 report. The same layering applies
to `Assessment`'s append-only guarantee (Contract §9): enforced by the
service surface (no `update`/`delete` method), not a SQLite trigger.

---

## 9. What this patch does **not** touch

`Worker.skills`, `Job.skill`, `Job.headcount`, `JobOffer`, `Shift`,
`ShiftEvent`, `TrustEngine`, `DispatchEngine` — all byte-for-byte unchanged.
No route was added. No confidence formula, dispatch fallback, availability
calendar, or crew concept was introduced. See the Patch 1 report for the
full file list and exact `git diff --stat`.
