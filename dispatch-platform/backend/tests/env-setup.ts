// Runs inside every test file's process before its tests execute (vitest
// `setupFiles`), so the Prisma client singleton in src/config/prisma.ts
// connects to the same throwaway test.db that tests/global-setup.ts just
// migrated — never prisma/dev.db.
process.env.DATABASE_URL = 'file:./test.db';
process.env.NODE_ENV = 'test';

// Patch 2 — Worker Capability API is this branch's first HTTP-level test
// (Contract §11), so it's the first thing to import `src/server.ts`, which
// pulls in `src/config/env.ts`. That module calls `required('JWT_SECRET')`
// with no fallback and throws at import time if it's unset — every prior
// test file avoided this entirely by talking to Prisma/services directly
// and never importing `env.ts`. Set a fixed, obviously-non-production value
// here rather than requiring a real `.env` file to exist for tests to run.
process.env.JWT_SECRET = process.env.JWT_SECRET ?? 'test-only-jwt-secret-do-not-use-in-prod';
