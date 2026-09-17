import { describe, it, expect, beforeAll } from 'vitest';
import { prisma } from '../src/config/prisma';
import { seedTaxonomy } from '../prisma/seeds/taxonomy';
import { CapabilityService } from '../src/services/capability.service';
import { AssessmentService } from '../src/services/assessment.service';
import * as h from './helpers';

async function makeCapability() {
  const { worker } = await h.createWorker();
  const task = await prisma.task.findUniqueOrThrow({ where: { code: 'FAN_INSTALLATION' } });
  return CapabilityService.createCapability({
    workerId: worker.id,
    taskId: task.id,
    level: 2,
    provenance: 'SELF_DECLARED',
  });
}

describe('Assessment', () => {
  beforeAll(async () => {
    await seedTaxonomy(prisma);
  });

  it('records an assessment against its WorkerCapability', async () => {
    const capability = await makeCapability();
    const assessment = await AssessmentService.record(capability.id, {
      type: 'PRACTICAL_VERIFICATION',
      result: 'Passed practical check on fan mounting and wiring',
      assessedBy: 'contractor-user-id-placeholder',
    });

    expect(assessment.workerCapabilityId).toBe(capability.id);
    expect(assessment.type).toBe('PRACTICAL_VERIFICATION');

    const list = await AssessmentService.listForCapability(capability.id);
    expect(list).toHaveLength(1);
    expect(list[0].id).toBe(assessment.id);
  });

  it.each(['SELF_DECLARATION', 'KNOWLEDGE_TEST', 'PRACTICAL_VERIFICATION', 'PERFORMANCE_REVIEW'] as const)(
    'accepts the approved assessment type %s',
    async (type) => {
      const capability = await makeCapability();
      const assessment = await AssessmentService.record(capability.id, {
        type,
        result: 'ok',
      });
      expect(assessment.type).toBe(type);
    },
  );

  it('rejects an assessment type outside the four approved types', async () => {
    const capability = await makeCapability();
    await expect(
      AssessmentService.record(capability.id, {
        // @ts-expect-error deliberately invalid for the test
        type: 'MADE_UP_TYPE',
        result: 'ok',
      }),
    ).rejects.toThrow();
  });

  it('404s for a nonexistent WorkerCapability', async () => {
    await expect(
      AssessmentService.record('00000000-0000-4000-8000-000000000000', {
        type: 'SELF_DECLARATION',
        result: 'ok',
      }),
    ).rejects.toThrow();
  });

  it('cascade-deletes its Assessments if the WorkerCapability is deleted', async () => {
    const capability = await makeCapability();
    await AssessmentService.record(capability.id, { type: 'SELF_DECLARATION', result: 'ok' });

    await prisma.workerCapability.delete({ where: { id: capability.id } });

    const remaining = await prisma.assessment.findMany({ where: { workerCapabilityId: capability.id } });
    expect(remaining).toHaveLength(0);
  });

  it('exposes no update/delete method — append-only by service surface, not just convention', () => {
    expect((AssessmentService as unknown as Record<string, unknown>).update).toBeUndefined();
    expect((AssessmentService as unknown as Record<string, unknown>).delete).toBeUndefined();
  });
});
