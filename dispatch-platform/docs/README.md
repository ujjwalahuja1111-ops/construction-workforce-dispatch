# Dispatch Platform — Handoff Documentation

Complete engineering handoff. Read in this order:

1. **[Architecture.md](Architecture.md)** — system overview, monorepo layout, the FastAPI proxy quirk
2. **[Database.md](Database.md)** — Prisma schema, every model, indexes, migration path to Postgres
3. **[API.md](API.md)** — every REST endpoint, request/response shapes, error codes
4. **[Authentication.md](Authentication.md)** — phone + OTP + JWT flow, production hardening
5. **[DispatchEngine.md](DispatchEngine.md)** — worker matching algorithm and scoring
6. **[ShiftEngine.md](ShiftEngine.md)** — the 13-state finite-state machine
7. **[TrustEngine.md](TrustEngine.md)** — trust score formula and tuning
8. **[Mobile.md](Mobile.md)** — Expo/RN Worker app screens, navigation, theme
9. **[Contractor.md](Contractor.md)** — Phase 2 spec (contractor web portal)
10. **[Admin.md](Admin.md)** — Phase 3 spec (admin web portal)
11. **[DevelopmentGuide.md](DevelopmentGuide.md)** — local setup, common tasks, debugging
12. **[DeploymentGuide.md](DeploymentGuide.md)** — Docker, cloud VM, K8s, mobile builds
13. **[KnownLimitations.md](KnownLimitations.md)** — every Phase-1 shortcut, in writing
14. **[Roadmap.md](Roadmap.md)** — what to build next, in what order

## Sub-30-minute onboarding

New engineer? Do this:

1. Skim **Architecture.md** (5 min).
2. Follow **DevelopmentGuide.md §2** to boot the backend + mobile locally (10 min).
3. Run the smoke test in **DevelopmentGuide.md §6** to confirm the stack works (3 min).
4. Read **KnownLimitations.md** cover-to-cover before writing any code (10 min).

## Test credentials

All accounts share the dev OTP: **`123456`**.

- Demo worker (has pending offers): `+919020001000` (Rajesh Kumar)
- Demo worker (has one closed shift): `+919020001001` (Suresh Yadav)
- Demo contractor: `+919010000001` (Sharma Constructions)
- Demo admin: `+919000000001`

Re-seed anytime: `cd backend && npx tsx prisma/seed.ts`.
