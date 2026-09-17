import { describe, it, expect, beforeAll } from 'vitest';
import { prisma } from '../src/config/prisma';
import { seedTaxonomy } from '../prisma/seeds/taxonomy';
import { CapabilityService } from '../src/services/capability.service';
import * as h from './helpers';

describe('WorkerCapability', () => {
  beforeAll(async () => {
    await seedTaxonomy(prisma);
  });

  it('creates a valid capability for a worker/task pair', async () => {
    const { worker } = await h.createWorker();
    const task = await prisma.task.findUniqueOrThrow({ where: { code: 'PLASTER' } });

    const capability = await CapabilityService.createCapability({
      workerId: worker.id,
      taskId: task.id,
      level: 2,
      provenance: 'SELF_DECLARED',
    });

    expect(capability.workerId).toBe(worker.id);
    expect(capability.taskId).toBe(task.id);
    expect(capability.level).toBe(2);
    expect(capability.provenance).toBe('SELF_DECLARED');
    // Reserved-for-later fields default to null/unset in this patch.
    expect(capability.confidence).toBeNull();
  });

  it('resolves worker <-> task relationship correctly', async () => {
    const { worker } = await h.createWorker();
    const task = await prisma.task.findUniqueOrThrow({ where: { code: 'BLOCKWORK' } });
    await CapabilityService.createCapability({
      workerId: worker.id,
      taskId: task.id,
      level: 1,
      provenance: 'SELF_DECLARED',
    });

    const capabilities = await CapabilityService.listCapabilitiesForWorker(worker.id);
    expect(capabilities).toHaveLength(1);
    expect(capabilities[0].task.code).toBe('BLOCKWORK');
  });

  it('enforces unique(workerId, taskId)', async () => {
    const { worker } = await h.createWorker();
    const task = await prisma.task.findUniqueOrThrow({ where: { code: 'FAULT_FINDING' } });

    await CapabilityService.createCapability({
      workerId: worker.id,
      taskId: task.id,
      level: 3,
      provenance: 'ASSESSED',
    });

    await expect(
      CapabilityService.createCapability({
        workerId: worker.id,
        taskId: task.id,
        level: 1,
        provenance: 'SELF_DECLARED',
      }),
    ).rejects.toThrow();
  });

  it.each([0, 5, -1, 2.5])('rejects an out-of-range level (%s)', async (level) => {
    const { worker } = await h.createWorker();
    const task = await prisma.task.findUniqueOrThrow({ where: { code: 'LEAKAGE_REPAIR' } });

    await expect(
      CapabilityService.createCapability({
        workerId: worker.id,
        taskId: task.id,
        // @ts-expect-error deliberately invalid for the test
        level,
        provenance: 'SELF_DECLARED',
      }),
    ).rejects.toThrow();
  });

  it('rejects a provenance value outside the four approved states', async () => {
    const { worker } = await h.createWorker();
    const task = await prisma.task.findUniqueOrThrow({ where: { code: 'PIPE_INSTALLATION' } });

    await expect(
      CapabilityService.createCapability({
        workerId: worker.id,
        taskId: task.id,
        level: 2,
        // @ts-expect-error deliberately invalid for the test
        provenance: 'MADE_UP_STATE',
      }),
    ).rejects.toThrow();
  });

  it.each(['SELF_DECLARED', 'ASSESSED', 'PRACTICALLY_VERIFIED', 'PERFORMANCE_CONFIRMED'] as const)(
    'accepts the approved provenance value %s',
    async (provenance) => {
      const { worker } = await h.createWorker();
      const task = await prisma.task.findUniqueOrThrow({ where: { code: 'BATHROOM_PLUMBING' } });
      const capability = await CapabilityService.createCapability({
        workerId: worker.id,
        taskId: task.id,
        level: 1,
        provenance,
      });
      expect(capability.provenance).toBe(provenance);
    },
  );

  it('404s for a nonexistent worker or task', async () => {
    const task = await prisma.task.findUniqueOrThrow({ where: { code: 'WIRING' } });
    await expect(
      CapabilityService.createCapability({
        workerId: '00000000-0000-4000-8000-000000000000',
        taskId: task.id,
        level: 1,
        provenance: 'SELF_DECLARED',
      }),
    ).rejects.toThrow();
  });

  it('does not touch Worker.skills — the legacy flat-skill column is unaffected', async () => {
    const { worker } = await h.createWorker({ skills: 'MASON,HELPER,WELDER' });
    const task = await prisma.task.findUniqueOrThrow({ where: { code: 'LIGHT_INSTALLATION' } });
    await CapabilityService.createCapability({
      workerId: worker.id,
      taskId: task.id,
      level: 4,
      provenance: 'PERFORMANCE_CONFIRMED',
    });

    const reloaded = await prisma.worker.findUniqueOrThrow({ where: { id: worker.id } });
    expect(reloaded.skills).toBe('MASON,HELPER,WELDER');
  });
});
