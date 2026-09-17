import { prisma } from '../src/config/prisma';
import { signToken } from '../src/utils/jwt';
import { RoleT } from '../src/types/domain';

let phoneCounter = 0;

/**
 * Creates a real User+Worker pair directly via Prisma. Patch 1 has no API
 * layer (see Contract §15), so these tests exercise services and the DB
 * directly rather than going through Express/supertest.
 */
export async function createWorker(overrides: Partial<{ skills: string; city: string; state: string }> = {}) {
  phoneCounter += 1;
  const user = await prisma.user.create({
    data: {
      phone: `+9199${(1000000 + phoneCounter).toString().padStart(7, '0')}`,
      role: 'WORKER',
      fullName: `Test Worker ${phoneCounter}`,
      isVerified: true,
    },
  });
  const worker = await prisma.worker.create({
    data: {
      userId: user.id,
      skills: overrides.skills ?? 'MASON,HELPER',
      city: overrides.city ?? 'Bengaluru',
      state: overrides.state ?? 'Karnataka',
    },
  });
  return { user, worker };
}

/**
 * Patch 2 — Worker Capability API test infrastructure. This is the
 * branch's first HTTP-level test file (see Contract §11), so this is the
 * first helper that needs to sign a real JWT rather than talk to Prisma
 * directly.
 *
 * Signs a token with the same shape `src/utils/jwt.ts#JwtPayload` expects
 * (`sub`/`role`/`phone`) and returns a ready-to-use `Authorization` header
 * value. For a role-mismatch (403) test there is no need for a real User
 * row at all — `requireRole` rejects on the token's `role` claim before any
 * DB lookup happens — so callers may pass a synthetic `{ id, role, phone }`
 * rather than a row from `createWorker()`.
 */
export function authHeader(user: { id: string; role: RoleT | string; phone: string }): string {
  return `Bearer ${signToken({ sub: user.id, role: user.role as RoleT, phone: user.phone })}`;
}
