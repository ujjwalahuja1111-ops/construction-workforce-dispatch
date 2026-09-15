# Roadmap

The plan for what comes after Phase 1. Milestones are cumulative — each
one assumes everything before it is done.

---

## Phase 1 — Worker App + Backend (SHIPPED)

- ✅ Node/Express/TS + Prisma backend
- ✅ Auth (phone + OTP + JWT)
- ✅ Data model (10 entities)
- ✅ Dispatch, Shift, Trust engines
- ✅ Worker mobile app (11 screens)
- ✅ Seed data + smoke-tested end-to-end
- ✅ Docs

---

## Phase 2 — Contractor Web Portal (2–3 weeks)

**Goal:** Contractors can self-serve — post jobs, watch fills, pay out.

### Backend
- `/api/contractor/*` routes (spec in `Contractor.md` §4).
- Wire `JobService.createAndDispatch` to `POST /api/contractor/jobs`.
- Contractor-owned projects + shifts endpoints.
- `POST /api/shifts/:id/rating` (contractor rates worker).
- **Re-dispatch on decline/expire** (see `KnownLimitations.md` §4.2).
- **Offer expiry sweeper** (§1.3).

### Portal
- Vite + React + TS scaffold in `contractor-web/`.
- Screens: Login, Dashboard, Projects, Jobs, Workers, Shifts, Attendance,
  Payments (basic), Settings. See `Contractor.md` §3.
- Polling every 15 s on active screens.

### Mobile changes
- Show contractor rating on shift detail once it exists.
- Push notification stub in the UI (unread badge on the bell).

**Exit criteria**
- A contractor can register (via admin provisioning), log in, post a job,
  watch it fill, mark paid, and rate the worker — all without touching curl.

---

## Phase 3 — Admin Portal (2 weeks)

**Goal:** Support and ops can run the platform without engineers.

### Backend
- `/api/admin/*` (spec in `Admin.md` §4).
- `AdminAuditLog` table + service.
- Force-transition + adjust-pay endpoints.
- Impersonation JWT flow (Admin §5).
- Config table + endpoint for tunables (dispatch weights, trust weights,
  skill/city registry).

### Portal
- Vite + React + TS scaffold in `admin-web/`.
- Screens per `Admin.md` §3.
- **2FA (TOTP)** — mandatory before any admin actually uses the portal.

**Exit criteria**
- Admin can onboard a contractor from scratch, suspend a bad-actor worker,
  moderate a rating, force-close a stuck shift — all from the web UI.

---

## Phase 4 — Push, real SMS, rate limits (1 week)

**Goal:** Get the platform ready to serve real users.

- `expo-notifications` → APN / FCM. Requires an EAS build.
- Real SMS provider (MSG91 for India; Twilio backup).
- Remove `DEV_OTP_CODE` from prod build; hash OTPs at rest.
- Rate limits on `/otp/*`.
- JWT rotation support (`DeploymentGuide.md` §7).
- `pino` structured logging + Sentry.
- `/metrics` endpoint + basic Grafana dashboard.

**Exit criteria**
- Ready for a friends-and-family beta.

---

## Phase 5 — Payments (2–3 weeks)

**Goal:** Money flows through the platform.

Path A — **payout escrow** (recommended for India):
- Contractors deposit an advance against a Job.
- On CLOSE, the platform releases the amount to the worker's UPI VPA or bank.
- Escrow is a wallet in Razorpay Route or Cashfree Payouts.

Path B — **rails-only** (simpler MVP):
- Contractor pays offline; the platform is a record-of-truth for what's owed.
- Add `Payment` model: `{ shiftId, amount, status, paidAt, method, ref }`.

Either way:
- Add `Payment` model to schema.
- Contractor endpoints under `/api/contractor/payments/*`.
- Worker screens: **Payouts** (replaces the current "Earnings" tab or
  extends it) showing pending vs paid.
- Payment retries + reconciliation cron.

**Exit criteria**
- A worker sees "₹1200 paid to your UPI" after the contractor closes the
  shift, in ≤ 5 minutes.

---

## Phase 6 — Reliability & scale (open-ended)

Only start when concurrent workers exceed a few hundred.

- **Horizontal scaling:** K8s Deployment 2+ replicas; migrations as Jobs.
- **Prisma pool tuning:** `connection_limit` per replica.
- **Redis:** rate limits, session revocation list, BullMQ for scheduled
  work (offer expiry, notification retries).
- **SSE / WebSocket** for real-time contractor dashboards.
- **Read replicas** for analytics.
- **Sharding by city** if the marketplace grows to ~50 cities.

---

## Phase 7 — Marketplace intelligence

Once we have volume data:

- **Surge pricing** — automatic wage suggestion when the fill rate for a
  skill/city dips below a threshold. (One-line schema change:
  `Job.surgeMultiplier: float @default(1.0)`; the UI adds a "Surge" chip.)
- **Predicted arrival time** — ETA on the contractor dashboard using
  Google Maps or an OSRM instance.
- **Skill certification** — a `Certification` model per worker per skill
  (photo of trade license, endorsed by contractors). Weighted into the
  dispatch score.
- **Fairness caps** — prevent the top 10% of workers monopolising all
  offers. Add a soft cap on offers-per-worker-per-day and rotate.

---

## Phase 8 — Beyond MVP items intentionally deferred

These are in the original spec's "do not build yet" list. Roadmap slot when
demand emerges:

- **QR check-in** — supervisor scans a per-shift QR on the worker's phone;
  bypasses GPS spoof.
- **Voice notes** — workers leave voice updates on active shifts.
- **Referral program** — worker A refers worker B; A gets a bonus when B
  completes their first 3 shifts.
- **Aadhaar verification** — KYC integration (DigiLocker or Karza API).
- **Background location** — always-on tracking during a shift (requires
  native build + explicit user consent + Play Store data-safety disclosure).
- **Offline synchronisation** — mutation queue with conflict resolution
  when workers reconnect.
- **Digital signatures** — worker signs an on-site contract on the phone
  screen at check-in.
- **AI features** — automatic skill inference from work history, natural
  language contractor commands ("hire 5 masons for tomorrow"), predictive
  no-show scoring.
- **Multi-language support** — Hindi, Kannada, Tamil, Telugu, Bengali,
  Marathi. Requires i18n plumbing (Phase 4 or 5) and translation partner.

---

## Rough sequencing

```
weeks   deliverable
─────   ─────────────────────────────────────────
1–3     Phase 2 (Contractor portal)
4–5     Phase 3 (Admin portal + 2FA)
6       Phase 4 (Push + real SMS + hardening) — beta launch
7–9     Phase 5 (Payments)                    — public launch
ongoing Phase 6 (Reliability), Phase 7 (Intelligence), Phase 8 (as needed)
```

---

## Non-negotiables before public launch

Before you flip DNS to real, paying users, every item below must be true:

1. `NODE_ENV=production` and `DEV_OTP_CODE` unset.
2. Real SMS provider in place, verified with 3 different phone numbers.
3. Rate limits on `/otp/*` (and on the accept endpoint — a bot could
   monopolise offers).
4. Admin 2FA.
5. Automated Postgres backups (daily + PITR).
6. Payments flow (Phase 5) — you cannot launch a labour marketplace with
   "we'll figure out payments later".
7. Terms of Service, Privacy Policy, and a Grievance Officer email.
8. Play Store listing accepted + at least one iOS test flight round.
9. `/metrics` scraped by Prometheus; a paging alert on `/api/health` 5xx.
10. Runbook for the top 10 incidents (Node down, Postgres down, dispatch
    stuck, worker check-in refused, SMS provider outage, …).

If any of these are missing, you're not launching — you're leaking users
into a broken product.
