# API Reference

All endpoints are versioned under **`/api`** and return JSON.

- **Base URL (dev, local Node):** `http://localhost:8002/api`
- **Base URL (Emergent preview):** `${EXPO_PUBLIC_BACKEND_URL}/api`
- **Authentication:** Bearer JWT in the `Authorization` header
  (except for OTP request/verify)
- **Content-Type:** `application/json` for every request with a body
- **Error shape:**
  ```json
  { "error": { "code": "STRING_CODE", "message": "human message", "details": {} } }
  ```
- **Common error codes:** `BAD_REQUEST`, `VALIDATION_ERROR`, `UNAUTHORIZED`,
  `FORBIDDEN`, `NOT_FOUND`, `CONFLICT`, `INVALID_STATE`, `INTERNAL`

---

## Table of contents

1. Health
2. Authentication
3. Worker
4. Jobs (offers)
5. Shifts
6. Notifications

---

## 1. Health

### `GET /api/health`
Public. Liveness probe.

**200**
```json
{ "status": "ok", "service": "dispatch-backend", "ts": "2026-01-01T00:00:00.000Z" }
```

---

## 2. Authentication

### `POST /api/auth/otp/request`
Public. Issues a one-time password to a phone.

**Body**
```json
{
  "phone": "+919020001000",         // or "9020001000" — normalised server-side
  "role": "WORKER"                  // optional; only WORKER can self-register
}
```

**200**
```json
{
  "userId": "uuid",
  "phone": "+919020001000",
  "isNewUser": false,
  "devOtp": "123456"                // ONLY in non-production. Remove in prod.
}
```

**403** if `role != WORKER` for a non-existent phone (contractors/admins must
be provisioned by an admin).

---

### `POST /api/auth/otp/verify`
Public. Verifies OTP and returns a JWT.

**Body**
```json
{ "phone": "+919020001000", "code": "123456" }
```

**200**
```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXV...",
  "user": {
    "id": "uuid",
    "phone": "+919020001000",
    "fullName": "Rajesh Kumar",
    "role": "WORKER",
    "isVerified": true
  },
  "profileComplete": true
}
```

**401** `UNAUTHORIZED` — code wrong / expired / already consumed.

---

## 3. Worker

All routes require `Authorization: Bearer <token>` **and** `role = WORKER`.

### `GET /api/worker/me`

**200**
```json
{
  "user":   { "id": "...", "phone": "+919...", "fullName": "...", "role": "WORKER" },
  "worker": {
    "id": "...", "skills": "MASON,HELPER", "experienceYears": 5, "dailyWage": 900,
    "city": "Bengaluru", "state": "Karnataka",
    "homeLatitude": 12.97, "homeLongitude": 77.59,
    "isAvailable": true, "trustScore": 81,
    "totalShifts": 20, "completedShifts": 16, "cancelledShifts": 0,
    "acceptedOffers": 22, "declinedOffers": 3, "avgRating": 4.2,
    "totalEarnings": 17595
  }
}
```

### `POST /api/worker/profile`
Complete or update the worker profile.

**Body**
```json
{
  "fullName": "Rajesh Kumar",
  "skills": ["MASON","HELPER"],
  "experienceYears": 5,
  "dailyWage": 900,
  "city": "Bengaluru",
  "state": "Karnataka",
  "homeLatitude": 12.9716,
  "homeLongitude": 77.5946
}
```

Skill codes: `MASON`, `HELPER`, `BAR_BENDER`, `CARPENTER`, `PAINTER`,
`ELECTRICIAN`, `PLUMBER`, `WELDER`, `TILE_LAYER`, `SUPERVISOR`.

Validation:
- `dailyWage`: 100..10000 (INR)
- `experienceYears`: 0..50
- `skills`: at least 1

### `POST /api/worker/location`
Update current GPS. Called opportunistically by the mobile app so dispatch
uses fresh location.

**Body** `{ "latitude": 12.9716, "longitude": 77.5946 }`

### `POST /api/worker/availability`
Master on/off switch. When `false`, dispatch skips the worker entirely.

**Body** `{ "available": true }`

### `GET /api/worker/offers`
Pending offers, sorted by dispatch `score` desc.

**200**
```json
{
  "offers": [
    {
      "id": "offer-uuid",
      "jobId": "job-uuid",
      "workerId": "worker-uuid",
      "status": "PENDING",
      "score": 0.72,
      "distanceKm": 2.1,
      "expiresAt": "2026-01-01T12:15:00.000Z",
      "job": {
        "skill": "MASON",
        "headcount": 3,
        "dailyWage": 850,
        "shiftDate": "2026-01-01T00:00:00.000Z",
        "startTime": "08:00",
        "endTime": "18:00",
        "notes": "Bring PPE",
        "project": {
          "name": "Whitefield Tower A",
          "siteAddress": "ITPL Main Road",
          "latitude": 12.98,
          "longitude": 77.75,
          "contractor": { "companyName": "Sharma Constructions Pvt Ltd" }
        }
      }
    }
  ]
}
```

### `GET /api/worker/shifts`
All shifts for the current worker, newest first. Same shape as `/shifts/:id`
minus the `events` array.

### `GET /api/worker/earnings`
**200**
```json
{
  "total": 17595,       // INR lifetime
  "week":  1200,        // INR last 7 days
  "month": 5400,        // INR last 30 days
  "shifts": [ /* up to 20 recent closed shifts */ ]
}
```

---

## 4. Jobs (offer actions)

### `POST /api/jobs/offers/accept`

**Body** `{ "offerId": "uuid" }`

**200**
```json
{
  "offer": { "id": "...", "status": "ACCEPTED", "respondedAt": "..." },
  "shift": { "id": "...", "state": "ACCEPTED", "wageAmount": 850, ... }
}
```

**Errors**
- `404 NOT_FOUND` — offer id doesn't exist
- `403 FORBIDDEN` — offer belongs to a different worker
- `422 INVALID_STATE` — offer already `ACCEPTED`/`DECLINED`/`EXPIRED`
- `409 CONFLICT` — the job was fully staffed before this accept
- Side effects:
  - other pending offers on the same job (for this worker) → `DECLINED`
  - if job now fully staffed → job status `FULFILLED` and remaining offers → `EXPIRED`
  - `Worker.acceptedOffers++`, `Worker.totalShifts++`
  - `TrustEngine.recompute(workerId)`

### `POST /api/jobs/offers/decline`

**Body** `{ "offerId": "uuid" }`

**200** `{ "offer": { "id": "...", "status": "DECLINED", "respondedAt": "..." } }`

Side effects: `Worker.declinedOffers++`, trust recomputed.

---

## 5. Shifts

All state-transition endpoints return the updated shift.

### `GET /api/shifts/active`
Returns the worker's currently in-flight shift, or `null` if none.

**200**
```json
{
  "shift": {
    "id": "...", "state": "WORKING",
    "job": { "skill": "MASON", "project": { "name": "..." } },
    "events": [ /* audit log */ ]
  }
}
```

### `GET /api/shifts/:id`
Full shift detail including `events[]` audit log.

### State transitions
Each takes an empty body unless noted.  Illegal transitions → **422** with
`code: "INVALID_STATE"`.  See `ShiftEngine.md` for the full transition graph.

| Endpoint                          | Requires body                              | Effect                                        |
|-----------------------------------|--------------------------------------------|-----------------------------------------------|
| `POST /shifts/:id/travel`         | `{ latitude?, longitude? }`                | ACCEPTED → TRAVELLING                         |
| `POST /shifts/:id/arrive`         | `{ latitude?, longitude? }`                | TRAVELLING → ARRIVED                          |
| `POST /shifts/:id/check-in`       | `{ latitude, longitude }` **required**     | ARRIVED → CHECKED_IN. **Rejects if > 500m from site** (`INVALID_STATE`). Sets `checkInAt`, `lateMinutes`. |
| `POST /shifts/:id/start-work`     | –                                          | CHECKED_IN → WORKING                          |
| `POST /shifts/:id/break`          | –                                          | WORKING → BREAK, or RESUMED → BREAK           |
| `POST /shifts/:id/resume`         | –                                          | BREAK → RESUMED                               |
| `POST /shifts/:id/complete`       | –                                          | WORKING/RESUMED → COMPLETED                   |
| `POST /shifts/:id/check-out`      | `{ latitude, longitude }` **required**     | COMPLETED → CHECKED_OUT. Sets `checkOutAt`, `workedMinutes`, `earlyExitMinutes`. |
| `POST /shifts/:id/close`          | –                                          | CHECKED_OUT → CLOSED. Finalises `amountEarned`, increments `Worker.completedShifts` and `Worker.totalEarnings`, recomputes trust. |

Cancellation branch (any non-terminal → `CANCELLED`) is coded in the engine
but **not yet exposed** as an endpoint. Add `POST /shifts/:id/cancel` when
contractor-cancel and worker-no-show flows land.

---

## 6. Notifications

### `GET /api/notifications`
Query params:
- `unread=true` — return only unread rows

**200**
```json
{
  "notifications": [
    { "id":"...", "type":"JOB_OFFER", "title":"New job offer",
      "body":"MASON · ₹850/day", "data":"{\"jobId\":\"...\"}",
      "readAt": null, "createdAt":"..." }
  ]
}
```

### `POST /api/notifications/:id/read`
Marks a single notification as read.

### `POST /api/notifications/read-all`
Marks every notification for the user as read.

---

## 7. HTTP status conventions

| Code | Meaning in this API                                     |
|------|---------------------------------------------------------|
| 200  | Success                                                 |
| 400  | Malformed request (bad JSON, missing field)             |
| 401  | Missing/expired bearer token or wrong OTP               |
| 403  | Authenticated but the role/ownership doesn't allow it   |
| 404  | Resource doesn't exist (or belongs to another user)     |
| 409  | Business conflict (job filled, offer taken)             |
| 422  | Legal-shape but illegal state transition                |
| 500  | Unhandled server error (bug — check logs)               |

Every non-200 body has the `{ error: { code, message, details? } }` shape.

---

## 8. Not yet implemented (see `Roadmap.md`)

- Contractor CRUD: `POST /api/contractor/projects`, `POST /api/contractor/jobs`, etc.
- Admin surface: `GET /api/admin/users`, `POST /api/admin/verify`, analytics.
- Ratings: `POST /api/shifts/:id/rating` (contractor rates worker).
- Cancellation endpoint.
- Websocket / SSE stream for real-time offer push.
