# Admin Web Portal — Phase 3 Spec

**Status:** Not implemented. Scaffolded at `dispatch-platform/admin-web/`.
This is the pick-up spec.

---

## 1. Purpose

Admins are the **operators** of the platform. They:

1. Onboard and verify contractors (Aadhaar/GST — future) and workers.
2. Handle disputes, force-close stuck shifts, reset trust scores.
3. Monitor platform-wide KPIs (fill rate, cancellation rate, revenue).
4. Curate skills and cities as the marketplace expands.

---

## 2. Tech stack

Same as the contractor portal (Vite + React + TS + react-query + react-router).
Reuse component library across both web portals.

---

## 3. Screens

### 3.1 Login
- Phone + OTP.
- Rejects if `user.role !== "ADMIN"`.
- 2FA: **must** ship before external launch — TOTP via `speakeasy`.

### 3.2 Overview (`/`)
Platform KPI dashboard:
- Total workers · verified % · avg trust
- Total contractors · active projects
- Jobs today (open · dispatching · fulfilled · cancelled)
- Fill rate (last 7 days) with a simple line chart
- Cancellation rate (last 7 days)
- Payments processed (once gateway lands)

### 3.3 Worker Management (`/workers`)
- Table with filters: city · skill · trust range · verified · active.
- Row actions:
  - **Verify identity** → flips `User.isVerified = true` (until we wire real KYC)
  - **Suspend** → `User.isActive = false`
  - **Recompute trust** → server-side `TrustEngine.recompute(workerId)`
  - **View history** → all their shifts, offers, ratings

### 3.4 Contractor Management (`/contractors`)
- Table with filters + verification, GST edit, suspension.
- Row action: **Impersonate** (admin-only endpoint that issues a scoped
  short-lived JWT for that contractor for support debugging).

### 3.5 Projects (`/projects`)
- Read-mostly. Force-close a project (ends all its jobs).

### 3.6 Jobs (`/jobs`)
- Global list. Filter by contractor / skill / status / date range.
- Row action: **Force cancel** — cancels all shifts + refunds.

### 3.7 Shift Monitoring (`/shifts`)
Real-time-ish operations screen:
- Filters: `state`, contractor, worker phone, date.
- Row action: **Force-transition** — pick a target state (dangerous; log
  aggressively). Backed by an admin-only endpoint that bypasses the state
  machine guard.

### 3.8 Analytics (`/analytics`)
- Fill rate by skill / city / day
- Trust score distribution
- Contractor retention (cohort chart)
- Worker retention

Phase-3 stops here; a proper BI stack (Metabase pointed at read replica) is
better than baking richer analytics into the admin UI.

### 3.9 User Verification queue (`/verify`)
Once KYC lands, admins triage uploaded IDs. For Phase 3 without KYC docs, this
is just a "mark verified" checkbox with a note.

### 3.10 Settings (`/settings`)
- Skills registry (add / rename / retire a skill code).
- Cities registry.
- Dispatch tuning: expose the scoring weights (`trust`, `acceptance`,
  `distance`, `workload`) as editable knobs (backed by env or a `Config`
  table).
- Trust weights: same pattern.

---

## 4. Backend endpoints to add (Phase 3)

All under `/api/admin`, all require `role = ADMIN`.

```
# Users
GET   /users?role=WORKER&city=...&verified=false
GET   /users/:id
PATCH /users/:id                   ({ isVerified, isActive, fullName, deletedAt })
POST  /users/:id/recompute-trust   (worker only)
POST  /users/:id/impersonate       (returns short-lived JWT; audit log)

# Projects / Jobs / Shifts (read-mostly + force operations)
GET   /projects
GET   /jobs
POST  /jobs/:id/force-cancel
GET   /shifts
POST  /shifts/:id/force-transition ({ toState, note })

# Ratings
DELETE /ratings/:id                (moderate abuse)

# Configuration
GET  /config                        (returns dispatch/trust weights + skill/city registries)
PATCH /config                       (audited change)

# Analytics
GET  /stats/overview
GET  /stats/fill-rate               (?groupBy=skill|city|day)
GET  /stats/trust-distribution
```

Every admin write should append to an `AdminAuditLog` table (add to schema):

```prisma
model AdminAuditLog {
  id        String   @id @default(uuid())
  adminId   String
  action    String
  target    String
  before    String?  // JSON snapshot
  after     String?  // JSON snapshot
  createdAt DateTime @default(now())

  @@index([adminId])
  @@index([createdAt])
}
```

---

## 5. Impersonation

Support debugging requires impersonation. Ship it with these rules:
- Admin calls `POST /api/admin/users/:id/impersonate`.
- Server returns a JWT with the target user's `sub`, `role`, `phone` **and**
  a `imp: adminId` claim.
- Backend middleware treats such tokens as normal auth but every controller
  logs the `imp` claim.
- TTL: 30 minutes. Non-renewable.
- Every impersonation writes to `AdminAuditLog`.
- The impersonated user's UI shows a persistent banner "You are being
  supported by Admin X" — required for trust.

---

## 6. Force transition

The state machine is strict for a reason (payment finalisation), so force
transition must:
- Be a separate endpoint (`POST /api/admin/shifts/:id/force-transition`) — not
  a bypass on the standard endpoint.
- Require a `note` string (non-empty).
- Insert a `ShiftEvent` with `note = "FORCED by admin ${adminId}: ${note}"`.
- Skip payment finalisation if the target is `CLOSED` (admin manually enters
  the final `amountEarned` in a second call to a `POST /shifts/:id/adjust-pay`
  endpoint).

---

## 7. Testing strategy

Same as contractor: Vitest + Playwright.  Seed admin `+919000000001`.

---

## 8. Security notes

- Admin JWTs should be shorter-lived (`JWT_EXPIRES_IN` overridden to `12h` on
  admin login).
- **Mandatory 2FA** before production launch. Enrolment flow: admin logs in,
  scans TOTP QR, verifies once; from then on every login requires the 6-digit
  code alongside the OTP.
- The admin portal should be served from a subdomain (`admin.dispatch.example`)
  and never share cookies with the marketing site.
