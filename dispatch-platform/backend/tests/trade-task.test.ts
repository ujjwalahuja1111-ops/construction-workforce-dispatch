import { describe, it, expect, beforeAll } from 'vitest';
import { prisma } from '../src/config/prisma';
import { seedTaxonomy, V1_TAXONOMY } from '../prisma/seeds/taxonomy';

describe('Trade / Task taxonomy', () => {
  beforeAll(async () => {
    await seedTaxonomy(prisma);
  });

  it('seeds exactly the V1 taxonomy Trades', async () => {
    const trades = await prisma.trade.findMany({ orderBy: { code: 'asc' } });
    const codes = trades.map((t) => t.code).sort();
    expect(codes).toEqual(['ELECTRICAL', 'MASONRY', 'PLUMBING']);
  });

  it('seeds every named Task under its correct Trade', async () => {
    for (const trade of V1_TAXONOMY) {
      const tradeRow = await prisma.trade.findUniqueOrThrow({ where: { code: trade.code } });
      for (const task of trade.tasks) {
        const taskRow = await prisma.task.findUnique({ where: { code: task.code } });
        expect(taskRow, `expected seeded task ${task.code}`).not.toBeNull();
        expect(taskRow!.tradeId).toBe(tradeRow.id);
      }
    }
  });

  it('Task belongs to its Trade via the relation, not just a bare id', async () => {
    const task = await prisma.task.findUniqueOrThrow({
      where: { code: 'BRICKWORK_NEW_WALL' },
      include: { trade: true },
    });
    expect(task.trade.code).toBe('MASONRY');
  });

  it('rejects a duplicate Trade code', async () => {
    await expect(
      prisma.trade.create({ data: { code: 'MASONRY', name: 'Duplicate Masonry' } }),
    ).rejects.toThrow();
  });

  it('rejects a duplicate Task code', async () => {
    const masonry = await prisma.trade.findUniqueOrThrow({ where: { code: 'MASONRY' } });
    await expect(
      prisma.task.create({
        data: { code: 'BRICKWORK_NEW_WALL', name: 'Duplicate', tradeId: masonry.id },
      }),
    ).rejects.toThrow();
  });

  it('running the taxonomy seed twice is idempotent (no duplicate rows)', async () => {
    const before = await prisma.task.count();
    const result = await seedTaxonomy(prisma);
    const after = await prisma.task.count();
    expect(after).toBe(before);
    expect(result.trades).toBe(V1_TAXONOMY.length);
    expect(result.tasks).toBe(V1_TAXONOMY.reduce((n, t) => n + t.tasks.length, 0));
  });

  it('refuses to delete a Trade referenced by a Task (Restrict, not Cascade)', async () => {
    const masonry = await prisma.trade.findUniqueOrThrow({ where: { code: 'MASONRY' } });
    await expect(prisma.trade.delete({ where: { id: masonry.id } })).rejects.toThrow();
  });

  it('refuses to delete a Task referenced by a WorkerCapability (Restrict, not Cascade)', async () => {
    const task = await prisma.task.findUniqueOrThrow({ where: { code: 'WIRING' } });
    const user = await prisma.user.create({
      data: { phone: '+919999900001', role: 'WORKER', fullName: 'Restrict Test Worker' },
    });
    const worker = await prisma.worker.create({
      data: { userId: user.id, skills: 'ELECTRICIAN', city: 'Delhi', state: 'Delhi' },
    });
    await prisma.workerCapability.create({
      data: { workerId: worker.id, taskId: task.id, level: 2, provenance: 'SELF_DECLARED' },
    });

    await expect(prisma.task.delete({ where: { id: task.id } })).rejects.toThrow();
  });
});
