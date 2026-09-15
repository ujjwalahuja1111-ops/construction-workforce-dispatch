# Mobile — Worker App

Native React Native app, Expo SDK 54, Android-first. Lives at
`/app/frontend/` (symlinked from `dispatch-platform/mobile`).

---

## 1. Tech stack

| Layer         | Choice                                            |
|---------------|---------------------------------------------------|
| Runtime       | Expo SDK 54, React Native 0.81                    |
| Router        | expo-router (file-based, `/app` folder)           |
| Language      | TypeScript 5.7                                    |
| Storage       | `@/src/utils/storage` (SecureStore under the hood)|
| Location      | `expo-location`                                   |
| Icons         | `@expo/vector-icons` (Ionicons)                   |
| Safe areas    | `react-native-safe-area-context`                  |

No CSS. No web-only libraries. No `className`.

---

## 2. Folder layout

```
frontend/
├── app/                          # expo-router routes (file-based)
│   ├── _layout.tsx               # Root Stack + AuthProvider + SafeAreaProvider
│   ├── index.tsx                 # Splash / initial redirect
│   ├── login.tsx                 # Phone entry
│   ├── otp.tsx                   # OTP verify
│   ├── register.tsx              # Complete worker profile
│   ├── notifications.tsx         # Notification list
│   ├── settings.tsx              # Settings + permissions
│   ├── trust.tsx                 # Trust score details
│   ├── shift/
│   │   └── [id].tsx              # Active shift management
│   └── (tabs)/
│       ├── _layout.tsx           # Bottom tab bar
│       ├── index.tsx             # Home dashboard
│       ├── jobs.tsx              # Available offers
│       ├── shifts.tsx            # Shift history
│       ├── earnings.tsx          # Earnings dashboard
│       └── profile.tsx           # Profile
└── src/
    ├── theme.ts                  # Design tokens (colors, spacing, radius, type)
    ├── api/
    │   └── client.ts             # Typed fetch wrapper
    ├── context/
    │   └── AuthContext.tsx       # Session + JWT + bootstrap
    ├── components/
    │   ├── Button.tsx            # Primary/secondary/danger/success button
    │   └── ui.tsx                # Card, Chip, StatTile, EmptyState, Label
    ├── hooks/                    # (from starter kit; icon-font prewarm)
    └── utils/
        └── storage/              # cross-platform key/value + secure store
```

---

## 3. Navigation graph

```
                    /
                    │  (Splash + redirect)
                    ▼
        ┌───────────┴───────────┐
        │                       │
      /login → /otp → /register (if new)
                       │
                       ▼
                  /(tabs)
                  ├── /(tabs)  (Home)
                  ├── /(tabs)/jobs
                  ├── /(tabs)/shifts
                  ├── /(tabs)/earnings
                  └── /(tabs)/profile
                            │
                            ├── /trust
                            ├── /settings
                            ├── /notifications
                            └── /shift/[id]
```

The root Stack is `headerShown: false` — every screen renders its own header,
so we can style them consistently and keep back buttons close to the thumb.

---

## 4. Design system

Tokens live in **`src/theme.ts`** — never import raw colour strings anywhere else.

**Palette rationale:** the app is used outdoors on construction sites in
harsh sunlight. High-contrast dark background + a bright safety-orange primary
scans instantly and stays glanceable through dust and glare.

| Token           | Value      | Purpose                             |
|-----------------|------------|-------------------------------------|
| `colors.bg`     | `#0A0A0B`  | canvas                              |
| `colors.surface`| `#161618`  | cards                               |
| `colors.primary`| `#FF6B00`  | primary action, highlights          |
| `colors.text`   | `#F5F5F7`  | body                                |
| `colors.success`| `#22C55E`  | closed shifts, positive metrics     |
| `colors.danger` | `#EF4444`  | errors, cancellations               |

**Sizing tokens:** `spacing` (8pt grid), `radius`, `type` (font scale).

**Touch targets:** minimum `touch.minHeight = 52` — larger than the 44/48
recommended baseline because workers often wear gloves.

**Icons:** `Ionicons` only — never emoji.

---

## 5. Auth context

`src/context/AuthContext.tsx` owns:

- `token`, `user`, `worker`, `profileComplete`, `loading`
- `setSession(token, user, profileComplete)` — used by the OTP screen
- `refreshMe()` — pulls `GET /worker/me` and merges into state
- `signOut()` — clears SecureStore and resets state

Behaviour:
- On mount, reads the token from SecureStore and calls `/worker/me`. If that
  fails (expired/invalid) the token is wiped and the user goes to `/login`.
- After a successful verify, we set the session with the JWT + user, then
  fire an async `me()` to hydrate the worker profile.
- `AuthProvider` is mounted **once**, at the root `_layout.tsx`, above the
  Stack — that's why every screen can `useAuth()` safely.

---

## 6. API client

`src/api/client.ts` exposes a single `api` object with typed methods:

```ts
await api.requestOtp('+919020001000');
await api.verifyOtp(phone, code);
await api.offers();
await api.acceptOffer(offerId);
await api.shiftAction(shiftId, 'check-in', { latitude, longitude });
```

Contract:
- Anonymous endpoints pass `{ anonymous: true }` internally.
- Every other call reads the bearer token from SecureStore and attaches it.
- Errors are thrown as `ApiException` with `status`, `code`, `message`,
  `details` fields. Screens catch this and render an inline error banner.
- Base URL comes from `EXPO_PUBLIC_BACKEND_URL` and is appended with `/api`.

---

## 7. Screens

### Splash / `app/index.tsx`
Reads `useAuth()` and redirects:
- loading → branded logo + spinner
- no token → `/login`
- token but no worker profile → `/register`
- token + profile → `/(tabs)`

### Login (`/login`)
Single 10-digit input, `+91` prefix locked, `Send OTP` primary CTA.  Shows
a dev-mode hint and a "Use demo worker" shortcut that pre-fills the number.

### OTP (`/otp`)
Auto-fills the code in dev mode from the router param. 30-second resend
countdown; resend re-hits `/otp/request`. Success → `AuthContext.setSession`
→ `/(tabs)` or `/register`.

### Register (`/register`)
Complete profile. Chip-based skill selector, number pads for wage and
experience, GPS opt-in via `expo-location`. No text inputs for skill — chips
only, to keep typing minimal.

### Home dashboard (`/(tabs)/index`)
Above the fold: greeting, availability toggle, trust score card, active shift
banner (if any). Below: this-week stats and the top 2 offer previews.
Pull-to-refresh + auto-refresh on focus.

### Jobs (`/(tabs)/jobs`)
Full list of pending offers, sorted by dispatch score. Each card:
- skill · wage · distance · date · scheduled hours
- contractor name · notes
- **Accept** (primary) and **Decline** (secondary) buttons — 50/50 split
- "Match X%" chip driven by `score * 100`

Accept navigates directly to `/shift/[id]` with the new active shift.

### Shift Detail (`/shift/[id]`)
The most important screen for on-site UX. Layout:
1. Big state banner (state name + wage chip)
2. Project card (name, address, coords, contractor)
3. Attendance card (once check-in fires)
4. Timeline (every `ShiftEvent` row)
5. **Sticky bottom action bar** with the single most likely next action:
   - `ACCEPTED` → **Start travelling**
   - `TRAVELLING` → **I have arrived**
   - `ARRIVED` → **Check in** (triggers GPS)
   - `CHECKED_IN` → **Start work**
   - `WORKING` → **Take a break** (primary) + **Finish work** (secondary)
   - `BREAK` → **Resume work**
   - `RESUMED` → **Finish work** + **Take a break** (secondary)
   - `COMPLETED` → **Check out** (triggers GPS)
   - `CHECKED_OUT` → **Close shift** (green button)

GPS-requiring actions call `Location.requestForegroundPermissionsAsync()` then
`getCurrentPositionAsync` and include the coords in the request body.

### Shift history (`/(tabs)/shifts`)
Chronological, most recent first. Colour-coded chip per state. Tapping a
non-terminal shift opens `/shift/[id]`.

### Earnings (`/(tabs)/earnings`)
Big "Lifetime earnings" hero card. Then side-by-side week/month tiles and a
recent payouts list.

### Profile (`/(tabs)/profile`)
Avatar (initials), skill chips, experience, wage, location. Links to
`/trust` and `/settings`. Sign-out button at the bottom.

### Trust (`/trust`)
Ring showing the score + a chip badge (Excellent/Good/Low). Below: the four
contributing factors (attendance, acceptance %, cancellations, avg rating)
with their raw values.

### Settings (`/settings`)
Account (phone, role), a `Linking.openSettings()` button for OS permissions,
version, sign-out.

### Notifications (`/notifications`)
List with unread border. Marks all read on mount.

---

## 8. Permissions

Only **foreground location** is used in Phase 1 (background is out of scope).
Declared in `app.json`:

```json
"android": { "permissions": ["ACCESS_COARSE_LOCATION","ACCESS_FINE_LOCATION"] },
"ios": {
  "infoPlist": {
    "NSLocationWhenInUseUsageDescription": "Verify site check-in and match nearby jobs"
  }
},
"plugins": [
  ["expo-location", {
    "locationAlwaysAndWhenInUsePermission": "Verify site check-in and match nearby jobs"
  }]
]
```

Request flow (per `handle_permissions_contract`):
1. Check current status.
2. Contextually request (only when the user actually taps a GPS-requiring button).
3. On denial with `canAskAgain === false`, show an "Open settings" CTA.
4. Never dead-end — the app still works without GPS for non-check-in flows.

---

## 9. Testing on device

- **Expo Go** (Android/iOS): scan the QR code — works for everything the MVP
  ships. Location works with the OS/browser prompt.
- **Native dev build:** needed only when you add native modules that aren't
  in Expo Go (background location, real push notifications, Bluetooth).
- **Web preview:** the app renders via React Native for Web — great for
  screenshot testing, but native APIs are shimmed.

---

## 10. Environment variables

`frontend/.env`:
- `EXPO_PUBLIC_BACKEND_URL` — base URL (no trailing slash). The API client
  appends `/api`.
- Do **not** modify `EXPO_PACKAGER_PROXY_URL` or `EXPO_PACKAGER_HOSTNAME`
  in Emergent.

---

## 11. Testing checklist for the mobile app

Once you make a UI change, run through this quick loop:

1. `yarn lint` — no ESLint errors.
2. Screenshot the Home dashboard (dark theme should be consistent).
3. Attempt sign-out and sign back in with a fresh phone (self-registration
   should still work).
4. Full shift lifecycle via `/shift/[id]` — every state transition should
   render its label in the sticky bar without a red screen.
5. Turn availability off in Home — new offers should stop arriving after the
   next server dispatch. Turn back on to resume.
