# Deployment Guide

How to run the platform in a real environment. Zero Emergent dependencies —
everything below is standard OSS tooling.

---

## 1. Targets covered

1. **Local (VS Code, docker-compose)** — for team development.
2. **Cloud VM** (single host, no orchestrator) — for the first prod run.
3. **Kubernetes / managed hosting** — for scale.
4. **Mobile builds** — Android APK / iOS TestFlight.

The `/app/backend/server.py` FastAPI reverse proxy is Emergent-only. **Do
not deploy it** to any of the targets above; the Node backend is the real
service.

---

## 2. Environment variables (backend)

Complete list from `.env.example`:

| Var                       | Example                                    | Notes                                    |
|---------------------------|--------------------------------------------|------------------------------------------|
| `NODE_ENV`                | `production`                               | Enables prod optimisations               |
| `PORT`                    | `8002`                                     | Backend listen port                      |
| `API_PREFIX`              | `/api`                                     | Prefix mounted on Express                |
| `DATABASE_URL`            | `postgresql://user:pass@host:5432/dispatch` | See §5 for Postgres switch               |
| `JWT_SECRET`              | 64-char random string                       | **Rotate on every deploy** (see §7)      |
| `JWT_EXPIRES_IN`          | `24h` in prod                              | Currently `30d` in dev                   |
| `DEV_OTP_CODE`            | (unset)                                    | **Must be unset in production**          |
| `OTP_TTL_SECONDS`         | `300`                                      | 5 minutes                                |
| `CORS_ORIGIN`             | `https://dispatch.example`                 | Comma-separated list or `*`              |
| `DISPATCH_MAX_RADIUS_KM`  | `25`                                       | Dispatch radius                          |
| `DISPATCH_MAX_CANDIDATES` | `15`                                       | Offers per job                           |

Add these when you wire the missing pieces:

| Var                       | Purpose                                    |
|---------------------------|--------------------------------------------|
| `SMS_PROVIDER`            | `msg91` \| `twilio` \| `aws-sns`           |
| `MSG91_AUTH_KEY`          | if `msg91`                                 |
| `TWILIO_ACCOUNT_SID`      | if `twilio`                                |
| `TWILIO_AUTH_TOKEN`       | if `twilio`                                |
| `RATE_LIMIT_REDIS_URL`    | Redis URL for `express-rate-limit`         |

---

## 3. Local docker-compose (recommended for team dev)

The skeleton lives at `docker/README.md`. Concretely:

```yaml
# dispatch-platform/docker-compose.yml
version: "3.9"
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: dispatch
      POSTGRES_PASSWORD: dispatch
      POSTGRES_DB: dispatch
    ports: ["5432:5432"]
    volumes: ["pgdata:/var/lib/postgresql/data"]

  backend:
    build:
      context: .
      dockerfile: docker/backend.Dockerfile
    environment:
      NODE_ENV: development
      PORT: "8002"
      DATABASE_URL: postgresql://dispatch:dispatch@db:5432/dispatch
      JWT_SECRET: dev-only-secret
      DEV_OTP_CODE: "123456"
      CORS_ORIGIN: "*"
    depends_on: [db]
    ports: ["8002:8002"]
    command: >
      sh -c "npx prisma migrate deploy &&
             npx tsx prisma/seed.ts &&
             node dist/server.js"

volumes:
  pgdata:
```

Bring up: `docker compose up --build`. The backend is at `localhost:8002`.
Point the mobile app at `http://<your-lan-ip>:8002`.

---

## 4. Cloud VM (single-host)

Any Ubuntu 22.04 box will do. Steps:

```bash
# 1. Install Node + Postgres
sudo apt update && sudo apt install -y postgresql nodejs npm nginx certbot

# 2. Create DB
sudo -u postgres createuser dispatch --pwprompt
sudo -u postgres createdb dispatch -O dispatch

# 3. Deploy code
git clone <repo> /opt/dispatch
cd /opt/dispatch/backend
cp .env.example .env    # fill in real values
npm ci
npx prisma generate
npx prisma migrate deploy
npm run build

# 4. Run under systemd
sudo tee /etc/systemd/system/dispatch-backend.service <<EOF
[Unit]
Description=Dispatch Backend
After=network.target postgresql.service

[Service]
Type=simple
User=deploy
WorkingDirectory=/opt/dispatch/backend
EnvironmentFile=/opt/dispatch/backend/.env
ExecStart=/usr/bin/node dist/server.js
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable --now dispatch-backend
sudo systemctl status dispatch-backend

# 5. TLS + reverse proxy
sudo tee /etc/nginx/sites-available/dispatch <<EOF
server {
  listen 80;
  server_name api.dispatch.example;
  location / {
    proxy_pass http://127.0.0.1:8002;
    proxy_set_header Host \$host;
    proxy_set_header X-Real-IP \$remote_addr;
  }
}
EOF
sudo ln -s /etc/nginx/sites-available/dispatch /etc/nginx/sites-enabled/
sudo certbot --nginx -d api.dispatch.example
```

---

## 5. Migrating SQLite → PostgreSQL

Two edits + a fresh migration:

1. **`backend/prisma/schema.prisma`**
   ```prisma
   datasource db {
     provider = "postgresql"
     url      = env("DATABASE_URL")
   }
   ```

2. **`.env`**
   ```
   DATABASE_URL=postgresql://dispatch:dispatch@localhost:5432/dispatch
   ```

3. **Wipe old SQLite migrations** (they're dialect-specific):
   ```bash
   rm -rf prisma/migrations
   npx prisma migrate dev --name init_postgres
   ```

The schema is dialect-agnostic in our code (no SQLite-only types), so this
is safe. Re-seed with `npx tsx prisma/seed.ts`.

If you need to preserve data from a live SQLite DB, use `pgloader`:
```bash
pgloader sqlite:///path/to/dev.db postgresql://dispatch:dispatch@localhost/dispatch
```

---

## 6. Kubernetes sketch

For anything above a few thousand concurrent users:

- **Backend Deployment** — 2+ replicas of the Node image; readiness probe
  against `/api/health`.
- **Postgres** — managed service (RDS, Cloud SQL) with a read replica for
  analytics.
- **Redis** (new) — for rate limiting and to hold offer TTL scheduling
  (Bull / BullMQ queue).
- **Ingress** with TLS via cert-manager.
- **Migrations** — as a K8s Job (`npx prisma migrate deploy`) that runs
  before Deployment rollout completes.
- **Secrets** — `JWT_SECRET`, `DATABASE_URL`, SMS keys in a K8s Secret
  (sealed-secrets or Vault-backed CSI).

Because the backend is stateless (no in-memory sessions), scaling is
horizontal without work. Watch out for:
- Sticky sessions **not** needed.
- Prisma connection pool — set `?connection_limit=10` per replica.
- Metro (mobile) is a dev-only concern; production ships a compiled bundle.

---

## 7. `JWT_SECRET` rotation

1. Generate a new secret: `openssl rand -hex 32`.
2. Add it as `JWT_SECRET_NEXT` in the environment.
3. Modify `verifyToken` to try `JWT_SECRET` first and fall back to
   `JWT_SECRET_NEXT` on failure. Sign new tokens with `JWT_SECRET`.
4. Deploy.
5. After all issued tokens age out (i.e. `JWT_EXPIRES_IN` has elapsed since
   deploy), swap: promote `JWT_SECRET_NEXT` → `JWT_SECRET`, remove the
   fallback.

Note: today the code only supports one secret. Adding the two-secret
fallback is the first change you should make before the first prod deploy.

---

## 8. Mobile builds

The Expo project can build directly via EAS (Expo Application Services) if
you have an Expo account, **or** classic `expo prebuild` + `gradle` /
`xcode` if you want full control.

### EAS route

```bash
cd mobile
npx expo login
npx eas build -p android --profile production
npx eas submit -p android           # → Google Play
npx eas build -p ios --profile production
npx eas submit -p ios               # → App Store Connect
```

EAS config lives at `frontend/eas.json` (managed by Emergent — do not edit
in Emergent workspaces; in a local checkout it's a normal file).

### Classic route

```bash
cd mobile
npx expo prebuild --platform android
cd android && ./gradlew assembleRelease
# APK at android/app/build/outputs/apk/release/app-release.apk
```

### Environment for prod builds

Set `EXPO_PUBLIC_BACKEND_URL=https://api.dispatch.example` in
`mobile/.env.production` before building. Verify the URL is embedded by
building a dev version first and inspecting the bundle.

---

## 9. Production checklist

Complete before flipping the DNS to real users:

- [ ] `NODE_ENV=production` set.
- [ ] `DEV_OTP_CODE` **removed** from env.
- [ ] Real SMS provider wired; verified end-to-end with a real phone.
- [ ] `JWT_SECRET` is random, rotated once already (so rotation is understood).
- [ ] Postgres backups: automated daily + WAL streaming to S3.
- [ ] Postgres monitoring: pg_stat_activity + slow query log.
- [ ] Rate limits enabled on `/otp/*`.
- [ ] Log shipping to a durable sink (CloudWatch / Loki / Papertrail).
- [ ] Uptime monitor pinging `GET /api/health` every minute.
- [ ] Error tracking (Sentry) wired in Node + mobile.
- [ ] All `console.log` calls in prod hot paths reviewed.
- [ ] `helmet` HSTS enabled.
- [ ] CORS allow-list narrow (not `*`).
- [ ] Terms of Service + Privacy Policy pages live and linked from the app.
- [ ] Play Store / App Store listings + screenshots.
- [ ] Load test the dispatch flow at 100× expected first-week volume.

---

## 10. Rollback

- **Backend:** re-deploy the previous Docker image / Git SHA. Migrations are
  forward-only, so ensure the previous binary can run against the new
  schema (all Phase-1 migrations are additive so far).
- **Mobile:** the App/Play Store rollout has a native rollback. For
  over-the-air JS updates (via EAS Update), publish the previous channel.
- **DB:** point-in-time recovery from the last WAL.

---

## 11. Observability

Minimum viable set:

- **Health check:** `GET /api/health`
- **Metrics:** expose `/metrics` in Prometheus format via `prom-client`
  when we get here.
- **Traces:** OpenTelemetry auto-instrumentation for Express + Prisma
  once we go multi-service.

For a first prod launch, log-only is fine. Add metrics before we do
horizontal scaling.
