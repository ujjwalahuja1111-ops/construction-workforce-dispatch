import { defineConfig } from 'vitest/config';

// Backend test config (Patch 1 / Milestone 0C). This branch was started
// clean from origin/main (per the patch's own git/workflow instructions),
// which has zero TypeScript test infrastructure — the original engineering
// audit's finding that no `.test.ts` files exist anywhere in the backend is
// still true of origin/main today. This config is written fresh for this
// patch, following the same recommended stack docs/KnownLimitations.md
// §7.1 already names (vitest + a throwaway SQLite file, never the dev
// database — see tests/global-setup.ts).
export default defineConfig({
  test: {
    environment: 'node',
    globalSetup: ['./tests/global-setup.ts'],
    setupFiles: ['./tests/env-setup.ts'],
    testTimeout: 20000,
    hookTimeout: 20000,
    // One shared SQLite file across the whole run; keep it single-threaded
    // so writes from different test files don't interleave.
    fileParallelism: false,
  },
});
