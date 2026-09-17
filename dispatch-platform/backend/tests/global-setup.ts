import { execSync } from 'child_process';
import path from 'path';
import fs from 'fs';

// Runs once before the whole test run, in its own process. (Re)creates a
// throwaway SQLite database at prisma/test.db from the committed
// migrations — never the dev database (prisma/dev.db), and never via
// `migrate reset` against anything but this dedicated test file.
export default async function globalSetup() {
  const backendRoot = path.resolve(__dirname, '..');
  const dbFile = path.resolve(backendRoot, 'prisma', 'test.db');

  for (const suffix of ['', '-journal', '-wal', '-shm']) {
    const p = dbFile + suffix;
    if (fs.existsSync(p)) fs.unlinkSync(p);
  }

  execSync('npx prisma migrate deploy', {
    cwd: backendRoot,
    stdio: 'inherit',
    env: { ...process.env, DATABASE_URL: 'file:./test.db' },
  });
}
