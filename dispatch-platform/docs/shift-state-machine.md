# Shift State Machine

Every shift is a strict directed graph. Illegal transitions throw HTTP 422 with
`error.code = "INVALID_STATE"`. Every state transition writes a `ShiftEvent` row
for a complete audit trail.

## States (13)

| State        | Meaning                                                |
|--------------|--------------------------------------------------------|
| CREATED      | Shift row created (rarely used in MVP — offers skip to ACCEPTED). |
| OFFERED      | Worker has been shown the offer.                       |
| ACCEPTED     | Worker tapped Accept. Wage is locked in.               |
| TRAVELLING   | Worker started travelling to site.                     |
| ARRIVED      | Worker reports arrival (not yet geofenced).            |
| CHECKED_IN   | GPS geofence validated (≤500m). `checkInAt` captured.  |
| WORKING      | Actively working.                                      |
| BREAK        | Paused.                                                |
| RESUMED      | Resumed after a break (can loop back to WORKING/BREAK).|
| COMPLETED    | Worker declared work finished.                         |
| CHECKED_OUT  | GPS check-out captured. Worked-minutes computed.       |
| CLOSED       | Terminal. Payment finalised, trust recomputed.         |
| CANCELLED    | Terminal branch (any non-terminal → CANCELLED).        |

## Transition graph

```
CREATED     → OFFERED, CANCELLED
OFFERED     → ACCEPTED, CANCELLED
ACCEPTED    → TRAVELLING, CANCELLED
TRAVELLING  → ARRIVED, CANCELLED
ARRIVED     → CHECKED_IN, CANCELLED
CHECKED_IN  → WORKING, CANCELLED
WORKING     → BREAK, COMPLETED, CANCELLED
BREAK       → RESUMED, CANCELLED
RESUMED     → WORKING, BREAK, COMPLETED, CANCELLED
COMPLETED   → CHECKED_OUT
CHECKED_OUT → CLOSED
CLOSED      → (terminal)
CANCELLED   → (terminal)
```

## Attendance rules
- **Check-in** requires GPS coordinates that fall within **500m** of the site
  (`Project.latitude/longitude`). Otherwise the request is rejected with
  `INVALID_STATE`.
- `lateMinutes` = `nowMinutes - scheduledStartMinutes` (clamped ≥ 0)
- `earlyExitMinutes` = `scheduledEndMinutes - nowMinutes` at check-out (clamped ≥ 0)

## Payment finalisation (on CLOSED)
```
workedMinutes  = checkOutAt - checkInAt
scheduledMins  = scheduledEnd - scheduledStart
ratio          = min(1, workedMinutes / scheduledMins)
amountEarned   = round(wageAmount × ratio)
```
`Worker.completedShifts++` and `Worker.totalEarnings += amountEarned` happen atomically.

## API mapping
| Transition          | Endpoint                              | Body        |
|---------------------|---------------------------------------|-------------|
| ACCEPTED → TRAVELLING | POST /api/shifts/:id/travel          | (empty)     |
| TRAVELLING → ARRIVED  | POST /api/shifts/:id/arrive          | (empty)     |
| ARRIVED → CHECKED_IN  | POST /api/shifts/:id/check-in        | `{ latitude, longitude }` |
| CHECKED_IN → WORKING  | POST /api/shifts/:id/start-work      | (empty)     |
| WORKING → BREAK       | POST /api/shifts/:id/break           | (empty)     |
| BREAK → RESUMED       | POST /api/shifts/:id/resume          | (empty)     |
| RESUMED → COMPLETED   | POST /api/shifts/:id/complete        | (empty)     |
| COMPLETED → CHECKED_OUT | POST /api/shifts/:id/check-out     | `{ latitude, longitude }` |
| CHECKED_OUT → CLOSED  | POST /api/shifts/:id/close           | (empty)     |
