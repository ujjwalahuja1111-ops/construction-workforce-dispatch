import { describe, it, expect, beforeAll } from 'vitest';
import request from 'supertest';
import { buildApp } from '../src/server';
import { prisma } from '../src/config/prisma';
import { seedTaxonomy } from '../prisma/seeds/taxonomy';
import { CapabilityService } from '../src/services/capability.service';
import { Role } from '../src/types/domain';
import * as h from './helpers';

/**
 * Patch 2 — Worker Capability API (Self-Declaration). The 12 tests required
 * by the approved contract (patch2-contract-v2.md §10), in the same order
 * they're listed there. This is the branch's first HTTP-level test file
 * (§11) — every request goes through `buildApp()` + supertest, not the
 * service layer directly, so these exercise the real routing/auth/
 * validation/error-handling chain, not just `CapabilityService`.
 */

const app = buildApp();
const API = '/api';

// A CONTRACTOR/ADMIN token never needs a real DB row: `requireRole` rejects
// on the JWT's `role` claim before any Prisma lookup happens.
const contractorAuth = h.authHeader({ id: '11111111-1111-4111-8111-111111111111', role: Role.CONTRACTOR, phone: '+919990000001' });
const adminAuth = h.authHeader({ id: '22222222-2222-4222-8222-222222222222', role: Role.ADMIN, phone: '+919990000002' });

async function taskByCode(code: string) {
  return prisma.task.findUniqueOrThrow({ where: { code } });
}

describe('Worker Capability API (Patch 2 — Self-Declaration)', () => {
  beforeAll(async () => {
    await seedTaxonomy(prisma);
  });

  // 1. 401 on both endpoints with no token.
  it('401s on both endpoints with no token', async () => {
    const post = await request(app).post(`${API}/worker/capabilities`).send({});
    expect(post.status).toBe(401);

    const get = await request(app).get(`${API}/worker/capabilities`);
    expect(get.status).toBe(401);
  });

  // 2. 403 on both endpoints with a CONTRACTOR or ADMIN token.
  it('403s on both endpoints with a CONTRACTOR or ADMIN token', async () => {
    const task = await taskByCode('WIRING');

    for (const auth of [contractorAuth, adminAuth]) {
      const post = await request(app)
        .post(`${API}/worker/capabilities`)
        .set('Authorization', auth)
        .send({ taskId: task.id, level: 2 });
      expect(post.status).toBe(403);

      const get = await request(app).get(`${API}/worker/capabilities`).set('Authorization', auth);
      expect(get.status).toBe(403);
    }
  });

  // 3. POST creates a new capability: provenance = SELF_DECLARED, 201, and
  //    exactly one Assessment(type: SELF_DECLARATION) row exists afterward.
  it('creates a new self-declared capability, 201, with exactly one Assessment row', async () => {
    const { user, worker } = await h.createWorker();
    const task = await taskByCode('BRICKWORK_NEW_WALL');

    const res = await request(app)
      .post(`${API}/worker/capabilities`)
      .set('Authorization', h.authHeader(user))
      .send({ taskId: task.id, level: 2 });

    expect(res.status).toBe(201);
    expect(res.body.capability).toMatchObject({
      taskId: task.id,
      level: 2,
      provenance: 'SELF_DECLARED',
      task: { code: 'BRICKWORK_NEW_WALL', tradeCode: 'MASONRY' },
    });
    expect(res.body.capability.workerId).toBeUndefined();

    const capability = await prisma.workerCapability.findUniqueOrThrow({
      where: { workerId_taskId: { workerId: worker.id, taskId: task.id } },
    });
    const assessments = await prisma.assessment.findMany({ where: { workerCapabilityId: capability.id } });
    expect(assessments).toHaveLength(1);
    expect(assessments[0].type).toBe('SELF_DECLARATION');
    expect(assessments[0].assessedBy).toBeNull();
  });

  // 4. POST with level = 0, 5, -1, 2.5 -> 400, nothing written (no
  //    WorkerCapability, no Assessment).
  it.each([0, 5, -1, 2.5])('rejects an out-of-range level (%s) with 400 and writes nothing', async (level) => {
    const { user, worker } = await h.createWorker();
    const task = await taskByCode('BLOCKWORK');

    const res = await request(app)
      .post(`${API}/worker/capabilities`)
      .set('Authorization', h.authHeader(user))
      .send({ taskId: task.id, level });

    expect(res.status).toBe(400);

    const capability = await prisma.workerCapability.findUnique({
      where: { workerId_taskId: { workerId: worker.id, taskId: task.id } },
    });
    expect(capability).toBeNull();
  });

  // 5. POST with a syntactically invalid taskId -> 400. With a well-formed
  //    but nonexistent (or inactive) taskId -> 404.
  it('400s on a syntactically invalid taskId', async () => {
    const { user } = await h.createWorker();
    const res = await request(app)
      .post(`${API}/worker/capabilities`)
      .set('Authorization', h.authHeader(user))
      .send({ taskId: 'not-a-uuid', level: 1 });
    expect(res.status).toBe(400);
  });

  it('404s on a well-formed but nonexistent taskId', async () => {
    const { user } = await h.createWorker();
    const res = await request(app)
      .post(`${API}/worker/capabilities`)
      .set('Authorization', h.authHeader(user))
      .send({ taskId: '00000000-0000-4000-8000-000000000000', level: 1 });
    expect(res.status).toBe(404);
  });

  it('404s on a well-formed but inactive taskId', async () => {
    const { user } = await h.createWorker();
    const activeTask = await taskByCode('FAN_INSTALLATION');
    const inactiveTask = await prisma.task.create({
      data: {
        tradeId: activeTask.tradeId,
        code: `INACTIVE_TASK_${Date.now()}`,
        name: 'Deactivated for test',
        isActive: false,
      },
    });

    const res = await request(app)
      .post(`${API}/worker/capabilities`)
      .set('Authorization', h.authHeader(user))
      .send({ taskId: inactiveTask.id, level: 1 });
    expect(res.status).toBe(404);
  });

  // 6. POST twice for the same (worker, task) while still SELF_DECLARED:
  //    second call -> 200, exactly one WorkerCapability row with the new
  //    level, and exactly two Assessment rows in chronological order.
  it('updates an existing self-declared capability in place on a second POST', async () => {
    const { user, worker } = await h.createWorker();
    const task = await taskByCode('LIGHT_INSTALLATION');

    const first = await request(app)
      .post(`${API}/worker/capabilities`)
      .set('Authorization', h.authHeader(user))
      .send({ taskId: task.id, level: 1 });
    expect(first.status).toBe(201);

    const second = await request(app)
      .post(`${API}/worker/capabilities`)
      .set('Authorization', h.authHeader(user))
      .send({ taskId: task.id, level: 3 });
    expect(second.status).toBe(200);
    expect(second.body.capability.level).toBe(3);
    expect(second.body.capability.id).toBe(first.body.capability.id);

    const rows = await prisma.workerCapability.findMany({
      where: { workerId: worker.id, taskId: task.id },
    });
    expect(rows).toHaveLength(1);
    expect(rows[0].level).toBe(3);

    const assessments = await prisma.assessment.findMany({
      where: { workerCapabilityId: rows[0].id },
      orderBy: { assessedAt: 'asc' },
    });
    expect(assessments).toHaveLength(2);
    expect(assessments.every((a) => a.type === 'SELF_DECLARATION')).toBe(true);
    expect(assessments[1].result).toContain('1 → 3');
  });

  // 7. POST against a (worker, task) whose capability was seeded directly
  //    (bypassing this API) as ASSESSED/PRACTICALLY_VERIFIED/
  //    PERFORMANCE_CONFIRMED -> 409; re-fetch confirms level/provenance are
  //    byte-for-byte unchanged, and no new Assessment row was created.
  it.each(['ASSESSED', 'PRACTICALLY_VERIFIED', 'PERFORMANCE_CONFIRMED'] as const)(
    'rejects with 409 and writes nothing when the existing capability is %s',
    async (provenance) => {
      const { user, worker } = await h.createWorker();
      const task = await taskByCode('FAULT_FINDING');

      const seeded = await CapabilityService.createCapability({
        workerId: worker.id,
        taskId: task.id,
        level: 2,
        provenance,
      });

      const res = await request(app)
        .post(`${API}/worker/capabilities`)
        .set('Authorization', h.authHeader(user))
        .send({ taskId: task.id, level: 4 });
      expect(res.status).toBe(409);

      const reloaded = await prisma.workerCapability.findUniqueOrThrow({ where: { id: seeded.id } });
      expect(reloaded.level).toBe(2);
      expect(reloaded.provenance).toBe(provenance);

      const assessments = await prisma.assessment.findMany({ where: { workerCapabilityId: seeded.id } });
      expect(assessments).toHaveLength(0);
    },
  );

  // 8. GET returns only the authenticated worker's own capabilities.
  it('GET only returns the authenticated worker\'s own capabilities', async () => {
    const { user: userA, worker: workerA } = await h.createWorker();
    const { user: userB, worker: workerB } = await h.createWorker();
    const taskA = await taskByCode('PIPE_INSTALLATION');
    const taskB = await taskByCode('BATHROOM_PLUMBING');

    await CapabilityService.createCapability({ workerId: workerA.id, taskId: taskA.id, level: 2, provenance: 'SELF_DECLARED' });
    await CapabilityService.createCapability({ workerId: workerB.id, taskId: taskB.id, level: 3, provenance: 'SELF_DECLARED' });

    const res = await request(app).get(`${API}/worker/capabilities`).set('Authorization', h.authHeader(userA));
    expect(res.status).toBe(200);
    expect(res.body.capabilities).toHaveLength(1);
    expect(res.body.capabilities[0].taskId).toBe(taskA.id);
    expect(res.body.capabilities.some((c: { taskId: string }) => c.taskId === taskB.id)).toBe(false);

    // Sanity: worker B's own view is unaffected by worker A's request above.
    const resB = await request(app).get(`${API}/worker/capabilities`).set('Authorization', h.authHeader(userB));
    expect(resB.body.capabilities).toHaveLength(1);
    expect(resB.body.capabilities[0].taskId).toBe(taskB.id);
  });

  // 9. GET for a worker with zero capabilities -> 200, { capabilities: [] }.
  it('GET returns 200 with an empty array for a worker with zero capabilities', async () => {
    const { user } = await h.createWorker();
    const res = await request(app).get(`${API}/worker/capabilities`).set('Authorization', h.authHeader(user));
    expect(res.status).toBe(200);
    expect(res.body).toEqual({ capabilities: [] });
  });

  // 10. Regression: this API never touches Worker.skills (the legacy
  //     flat-skill column) — same style of check as Patch 1's own
  //     equivalent test in capability.test.ts, exercised here through the
  //     HTTP layer instead of the service directly.
  it('does not touch Worker.skills — the legacy flat-skill column is unaffected', async () => {
    const { user, worker } = await h.createWorker({ skills: 'MASON,HELPER,WELDER' });
    const task = await taskByCode('BRICKWORK_REPAIR');

    const res = await request(app)
      .post(`${API}/worker/capabilities`)
      .set('Authorization', h.authHeader(user))
      .send({ taskId: task.id, level: 2 });
    expect(res.status).toBe(201);

    const reloaded = await prisma.worker.findUniqueOrThrow({ where: { id: worker.id } });
    expect(reloaded.skills).toBe('MASON,HELPER,WELDER');
  });

  // 11. Regression: nothing this API ever writes sets confidence,
  //     restrictions, or evidenceRef to anything other than what Patch 1
  //     already leaves them as (null on a fresh row).
  it('never sets confidence, restrictions, or evidenceRef', async () => {
    const { user, worker } = await h.createWorker();
    const task = await taskByCode('LEAKAGE_REPAIR');

    await request(app)
      .post(`${API}/worker/capabilities`)
      .set('Authorization', h.authHeader(user))
      .send({ taskId: task.id, level: 1 });
    await request(app)
      .post(`${API}/worker/capabilities`)
      .set('Authorization', h.authHeader(user))
      .send({ taskId: task.id, level: 2 });

    const reloaded = await prisma.workerCapability.findUniqueOrThrow({
      where: { workerId_taskId: { workerId: worker.id, taskId: task.id } },
    });
    expect(reloaded.confidence).toBeNull();
    expect(reloaded.restrictions).toBeNull();
    expect(reloaded.evidenceRef).toBeNull();
  });

  // 12. Regression: a request body containing an extra workerId or
  //     provenance field is accepted (extra fields don't error) but has
  //     zero effect — the written row always reflects the JWT-derived
  //     worker and hardcoded SELF_DECLARED, never the extra field's value.
  it('accepts but ignores an extra workerId/provenance field in the body', async () => {
    const { user, worker } = await h.createWorker();
    const { worker: otherWorker } = await h.createWorker();
    const task = await taskByCode('WIRING');

    const res = await request(app)
      .post(`${API}/worker/capabilities`)
      .set('Authorization', h.authHeader(user))
      .send({ taskId: task.id, level: 3, workerId: otherWorker.id, provenance: 'PERFORMANCE_CONFIRMED' });

    expect(res.status).toBe(201);
    expect(res.body.capability.provenance).toBe('SELF_DECLARED');

    const mine = await prisma.workerCapability.findUnique({
      where: { workerId_taskId: { workerId: worker.id, taskId: task.id } },
    });
    expect(mine).not.toBeNull();
    expect(mine!.provenance).toBe('SELF_DECLARED');

    const other = await prisma.workerCapability.findUnique({
      where: { workerId_taskId: { workerId: otherWorker.id, taskId: task.id } },
    });
    expect(other).toBeNull();
  });
});
