# Docker (skeleton)

Phase 1 does **not** ship a working docker-compose yet. This directory reserves
the location and drops in a minimal Dockerfile for the Node backend.

## Backend image

```dockerfile
# docker/backend.Dockerfile
FROM node:20-alpine
WORKDIR /app
COPY backend/package*.json ./
COPY backend/prisma ./prisma
RUN npm ci --omit=dev && npx prisma generate
COPY backend/ .
RUN npm run build
EXPOSE 8002
CMD ["node", "dist/server.js"]
```

## docker-compose.yml (recommended shape)

```yaml
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
    build: { context: .., dockerfile: docker/backend.Dockerfile }
    environment:
      DATABASE_URL: postgresql://dispatch:dispatch@db:5432/dispatch
      JWT_SECRET: change-me
      PORT: "8002"
    depends_on: [db]
    ports: ["8002:8002"]

volumes:
  pgdata:
```

To switch Prisma to Postgres, change `backend/prisma/schema.prisma`:
```prisma
datasource db {
  provider = "postgresql"
  url      = env("DATABASE_URL")
}
```
Then `npx prisma migrate dev` will generate a fresh Postgres migration.
