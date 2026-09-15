# Authentication

Phone + OTP + JWT. Simple to implement, easy to harden for prod.

---

## 1. Flow

```
┌──────────┐  1. POST /api/auth/otp/request { phone }
│  Client  │─────────────────────────────────────────►
└──────────┘                                            ┌─────────────┐
                                                        │  Backend    │
      ◄──────────────────────────────────────────────── │             │
      2. { userId, phone, isNewUser, devOtp? }          │             │
                                                        │  - Normalise│
┌──────────┐  3. POST /api/auth/otp/verify              │    phone    │
│  Client  │     { phone, code }                        │  - Upsert   │
└──────────┘─────────────────────────────────────────►  │    user     │
                                                        │  - Store OTP│
                                                        └─────────────┘
      ◄──────────────────────────────────────────────── ┌─────────────┐
      4. { token, user, profileComplete }               │  Backend    │
                                                        │  - Verify   │
                                                        │  - Sign JWT │
                                                        └─────────────┘
```

Every subsequent request carries the JWT in `Authorization: Bearer <token>`.

---

## 2. Phone normalisation

- Input can be `+919020001000`, `919020001000`, `9020001000`, `+91 90200-01000`.
- `AuthService.normalizePhone` strips non-digits, takes the last 10 digits,
  prepends `+91`. Only Indian numbers are supported in Phase 1.
- Non-10-digit input throws **`400 BAD_REQUEST`**.

To support other countries, add a `countryCode` field and route by length.

---

## 3. OTP mechanics (dev)

- OTP code is the constant `env.devOtpCode = "123456"`.
- On `/otp/request` we insert an `Otp` row for the user with
  `expiresAt = now + OTP_TTL_SECONDS` (default 300 s = 5 min) and log the code
  to server stdout.
- The response payload includes `devOtp: "123456"` — this lets automated tests
  read the code without polling logs. **This field must be removed in prod
  builds** (`env.nodeEnv === "production"` already does this in code).
- `/otp/verify` picks the most recent unconsumed non-expired OTP for the user
  and matches on the code. On success: `Otp.consumed = true` and
  `User.isVerified = true`.

Not implemented in Phase 1 but easy to add:
- **Rate limiting** on `/otp/request` — max 3 requests / 15 min / phone.
- **Attempt cap** on `/otp/verify` — after 5 wrong attempts on the same OTP,
  mark the OTP consumed to force a resend.
- **OTP hashing** — currently stored plaintext because dev-only. In prod,
  store `bcrypt.hash(code)` and compare.

---

## 4. JWT

- Algorithm: HS256.
- Payload: `{ sub: userId, role, phone }`.
- Expiry: `env.jwtExpiresIn` (default `30d`). Consider dropping to `24h` in
  prod and issuing a refresh flow.
- Signed with `env.jwtSecret`. **Rotate this on prod deploy** and make sure
  the previous secret is retired only after tokens age out.

Verification lives in `middleware/auth.ts`:
- Missing header → `401 UNAUTHORIZED`.
- Bad signature / expired → `401 UNAUTHORIZED`.
- Otherwise `req.auth = { sub, role, phone }` is set and passed downstream.

---

## 5. Roles

Three constants in `types/domain.ts`:
- `WORKER` — mobile app.
- `CONTRACTOR` — Phase 2 web portal.
- `ADMIN` — Phase 3 web portal.

Route enforcement via `requireRole(...)`:
```ts
r.use(requireAuth, requireRole(Role.WORKER));
```
Any authenticated request whose `req.auth.role` isn't in the allow-list gets
`403 FORBIDDEN`.

Only `WORKER` accounts can self-register from an OTP request (auto-creates a
`User` row). Contractors and Admins **must** be provisioned by an admin —
requesting an OTP for a non-existent contractor phone returns `403`.

---

## 6. Session lifecycle on the mobile app

1. User taps **Send OTP** → API returns `devOtp` in dev.
2. OTP screen auto-fills it in dev mode; user taps **Verify**.
3. `AuthContext.setSession` writes the token to Expo SecureStore under key
   `dispatch.auth.token` and updates the in-memory session.
4. On next app launch, `AuthContext.bootstrap()` reads the token and calls
   `/worker/me`. On failure it wipes the token — the user re-authenticates.
5. `signOut()` removes the token and resets state.

The client never persists the OTP, only the JWT.

---

## 7. Password reset / recovery

There is no password. Recovery = re-authenticate with OTP. The phone is the
sole identity anchor. Users who lose their phone number lose their account
until an admin manually reassigns.

---

## 8. Hardening checklist for production

- [ ] Replace `DEV_OTP_CODE` with a random 6-digit generator (`crypto.randomInt`).
- [ ] Remove the `devOtp` field from `/otp/request` response when `NODE_ENV=production`.
- [ ] Hash OTP codes at rest (bcrypt with cost 8 — OTPs are short-lived).
- [ ] Wire an SMS provider (MSG91 / Twilio / AWS SNS) in a new
      `AuthService.sendOtpViaSms()` method (add the placeholder).
- [ ] Rate-limit `/otp/request` and `/otp/verify` per phone and per IP.
      Recommended: `express-rate-limit` backed by Redis.
- [ ] Rotate `JWT_SECRET` (support two active secrets during rotation window).
- [ ] Drop JWT expiry to `24h` and add a refresh token flow.
- [ ] Add **2FA (TOTP)** for `ADMIN` role.
- [ ] Add `AdminAuditLog` (see `Admin.md`).
- [ ] HTTPS-only cookie for the web portals if we move JWT into an HttpOnly
      cookie (currently in `localStorage` — vulnerable to XSS).
- [ ] Enable `helmet` HSTS explicitly in prod.
- [ ] Emit login/verify events to a security-events sink.

---

## 9. Common pitfalls

- **OTP already consumed** — re-requesting an OTP inserts a fresh row; the
  latest unconsumed one wins on verify. If a user hits "Resend" twice, only
  the last code works.
- **Wrong phone format** — `+91 09020 01000` will normalise to `+919020001000`
  because we take the last 10 digits (`9020001000`). Nine-digit numbers throw.
- **Token in URL** — never do this; always keep it in `Authorization`.
- **Clock skew** — JWT `exp` is UTC; if a device clock is 5 min ahead the
  token will still be valid on the server but the client might treat it as
  expired. Add a 30 s leeway in the mobile bootstrap check when we notice
  this in the field.
