# Development Guide

Everything you need to get productive on the codebase in under 30 minutes.

---

## 1. Prerequisites

- **Node.js ≥ 20**
- **npm ≥ 10** (yarn 1.x also fine)
- **Git**
- For mobile: **Expo Go** on an Android device (or an Android emulator)
- Optional: **VS Code** with the following extensions
  - Prisma
  - ESLint
  - Prettier
  - Expo Tools
  - React Native Tools

Recommended: Node via `nvm` or `fnm`. The repo has no `.nvmrc` yet — add one
if the team standardises.

---

## 2. First-time setup

```bash
# Clone
git clone <repo-url> dispatch-platform
cd dispatch-platform

# Backend
cd backend
cp .env.example .env
npm install
npx prisma generate
npx prisma migrate dev --name init
npx tsx prisma/seed.ts
npm run dev
# → http://localhost:8002/api/health

# Mobile (in a new terminal, at repo root)
cd mobile           # symlink to /app/frontend on Emergent; a plain dir in local checkouts
yarn install
# Point the app at your backend by editing .env:
#   EXPO_PUBLIC_BACKEND_URL=http://<your-lan-ip>:8002
yarn start
# → Scan QR with Expo Go on your Android device
```

**Emergent workspaces:** everything above is already done; the `expo` and
`backend` supervisor programs start automatically. The FastAPI proxy at
`/app/backend/server.py` transparently spawns the Node backend on port 8002.

---

## 3. Repo layout at a glance

```
backend/
├── src/                # See Architecture.md for the layered breakdown
├── prisma/schema.prisma    # single source of truth for the data model
└── prisma/seed.ts          # deterministic seed script
mobile/                 # Expo app
docs/                   # This documentation set
shared/types.ts         # cross-project types
```

---

## 4. Common tasks

### Add a new API endpoint
1. Add the Zod schema in `controllers/<domain>.controller.ts` (co-located).
2. Add the controller function that calls a service method.
3. Add / extend the service method in `services/<domain>.service.ts`.
4. Wire the route in `routes/<domain>.routes.ts`.
5. Restart is not required — `tsx watch` reloads on save.
6. Test with `curl` or Postman before touching the frontend.

### Add a new column to a model
1. Edit `prisma/schema.prisma`.
2. `npx prisma migrate dev --name <descriptive_name>` — this creates a new
   migration folder and regenerates the Prisma client.
3. Update the seed if the new column needs default data.
4. Update the service(s) that write to the model.
5. Add the field to any API response the client already consumes.

### Add a new mobile screen
1. Create the file under `app/` (expo-router picks it up automatically).
2. For routes inside the tab layout, place under `app/(tabs)/`.
3. Reuse `Card`, `Chip`, `Button`, `StatTile` from `src/components/`.
4. Read colours from `src/theme.ts` — never inline `#hex` values except for
   colours that must stay identical in light and dark mode.
5. Add `testID` to every interactive element (`kebab-case`, describes role).

### Add a new engine
1. Create `backend/src/engines/<name>.engine.ts`.
2. Keep it pure — no HTTP, no logging beyond `console.error` for panics.
3. Export a class with static methods. Prisma access is fine but pass IDs
   in, not entities (so the engine controls its own load).
4. Wire it into the service that owns the domain (never call an engine
   from a controller).

### Reset the database
```bash
cd backend
npx prisma migrate reset --force    # drops + re-applies all migrations
npx tsx prisma/seed.ts              # re-seed
```

### Run the type-checker
```bash
cd backend && npx tsc --noEmit
cd ../mobile && npx tsc --noEmit
```

Both should exit 0 with no output.

### Lint
```bash
cd mobile && yarn lint
```

---

## 5. Debugging

### Backend

- **Logs (Emergent):** `/var/log/supervisor/dispatch-backend.log`
- **Logs (local):** the console where `npm run dev` runs
- **Prisma queries:** set `log: ['query', 'warn', 'error']` in
  `src/config/prisma.ts` temporarily.
- **Inspect the DB:** `npx prisma studio` (opens a browser UI at :5555).

### Mobile

- **Logs:** the terminal running `yarn start`; also the in-app dev overlay
  (shake device → **Debug** or press `j` in the terminal for Chrome DevTools).
- **Network:** enable Flipper or use the browser dev tools on the web
  preview.

### Emergent-specific

- `sudo supervisorctl status` — check every service.
- `sudo supervisorctl restart backend` — restart the FastAPI proxy (also
  bounces the Node subprocess it spawns).
- `sudo supervisorctl restart expo` — restart Metro/Expo.
- **Do not** edit `/etc/supervisor/conf.d/supervisord.conf` — it's managed.

---

## 6. Testing

### Backend

- Unit tests: **not yet written**. Start with pure functions in
  `utils/geo.ts` and `engines/shift.engine.ts`. Suggested runner: `vitest`
  (no config needed for a TS project).
- Integration tests: use the pytest suite the testing agent wrote at
  `/app/backend/tests/test_dispatch_backend.py` as a starting point for a
  Node-native test using `supertest`.

### Manual smoke test (5 min)

```bash
BASE=http://localhost:8002/api

# Request + verify OTP
curl -s -X POST $BASE/auth/otp/request \
  -H 'content-type: application/json' \
  -d '{"phone":"+919020001000"}'

TOKEN=$(curl -s -X POST $BASE/auth/otp/verify \
  -H 'content-type: application/json' \
  -d '{"phone":"+919020001000","code":"123456"}' | jq -r .token)

# List offers
curl -s $BASE/worker/offers -H "authorization: Bearer $TOKEN" | jq

# Accept the first offer
OFFER=$(curl -s $BASE/worker/offers -H "authorization: Bearer $TOKEN" | jq -r '.offers[0].id')
curl -s -X POST $BASE/jobs/offers/accept \
  -H "authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' \
  -d "{\"offerId\":\"$OFFER\"}" | jq
```

---

## 7. Code style

- **TypeScript strict mode** is on (`tsconfig.json`). Never disable it.
- **No `any`** unless commented with the reason.
- **Named exports** for shared modules; default export only for React
  components required by expo-router.
- **JSDoc comments** on non-obvious functions and engines; no comments on
  trivial getters.
- **Prisma queries co-located** with the service that owns them. If the
  same query starts appearing in three places, promote it to a repository
  (`repositories/<name>.repo.ts`).

### Naming

- Files: `kebab-case.ts` (e.g. `job.service.ts`).
- Classes: `PascalCase`.
- Functions and variables: `camelCase`.
- Env vars: `SCREAMING_SNAKE_CASE`.
- Test IDs on mobile: `kebab-case` describing the role
  (`offer-accept-button`, not `blue-pill`).

### Commit messages

`type(scope): message` — for example:
- `feat(dispatch): add workload penalty`
- `fix(shift): allow WORKING→COMPLETED directly`
- `docs(api): document contractor endpoints`

Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`.

---

## 8. Working with expo-router

- Every file in `app/` is a route. Sub-folders become path segments.
- Bracketed names are dynamic: `app/shift/[id].tsx` → `/shift/:id`.
- Route groups (parentheses like `(tabs)`) don't affect the URL; they group
  layouts.
- The **root layout** must render a `<Stack>` (or `<Tabs>`), never bare
  `<Slot />`.
- Read params with `useLocalSearchParams()`.

---

## 9. Working with Prisma

- Never write raw SQL unless you also add an integration test.
- Prefer `select` in reads that go to the API — projecting explicitly is
  cheaper and safer than `include: { everything: true }`.
- Wrap multi-write operations in `prisma.$transaction`.
- `findUnique` throws only if the input is malformed; a missing row returns
  `null`. Always check for `null` explicitly.
- `updateMany` returns `{ count }` — it does not fail if 0 rows match, so
  guard with a preceding `count` when the operation must affect something.

---

## 10. Working with the mobile app

- Every screen should call `useSafeAreaInsets()` and pad accordingly — never
  hardcode `44` or `24` for the notch.
- Wrap text in `<Text>`. Never render raw strings inside `<View>`.
- All colors from `src/theme.ts`. New colours added there first, then used
  by components.
- `StyleSheet.create({...})` per file. No inline styles for anything
  reusable.
- Buttons must have `testID`, `accessibilityRole="button"`, and be at least
  `52 pt` tall (`touch.minHeight`).

---

## 11. Where to look when something breaks

| Symptom                             | First place to check                                      |
|-------------------------------------|-----------------------------------------------------------|
| API returns 502                     | Node backend down — `sudo supervisorctl status`, then the log |
| Mobile app is blank white           | Metro error — the Expo terminal will show a red trace     |
| `Cannot read properties of null`   | Bootstrap timing — often `useAuth()` before `AuthProvider`|
| Prisma error `column does not exist`| Missing migration — run `npx prisma migrate dev`          |
| Compilation error on `tsx watch`    | The console shows the file + line; fix and save         |
| Test agent report has failures      | Read the JSON at `/app/test_reports/iteration_N.json` and start with the first failure |

---

## 12. FAQ

**Q: Where do I set feature flags?**
A: There are none yet. Add a `Config` table (see `Admin.md` §3.10) rather
than env vars once you need per-tenant flags.

**Q: Is there hot reload?**
A: Yes — the backend runs under `tsx watch`, and Expo reloads the mobile
app on save. If a reload gets stuck, kill and restart the supervisor
program.

**Q: Can I use `console.log` for debugging?**
A: Yes, but strip it before merging. Prefer `console.error` for anything
you want to survive.

**Q: How do I add a new dependency?**
A: `cd backend && npm i <pkg> --save` (or `--save-dev`). For mobile:
`cd mobile && yarn expo install <pkg>` (`yarn expo install` picks the
SDK-compatible version).
