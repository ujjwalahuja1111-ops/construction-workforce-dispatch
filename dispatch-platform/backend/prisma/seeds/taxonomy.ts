/**
 * Idempotent seed for the Patch 1 / Milestone 0C capability taxonomy
 * (Trade -> Task). Safe to run repeatedly — every row is `upsert`ed on its
 * stable `code`, never created from a generated/incremented id — and safe
 * to run standalone (`npm run seed:taxonomy`), independent of the
 * destructive full-reset legacy seed in `prisma/seed.ts` (which does not
 * touch the Trade/Task tables at all, so this never fights with it).
 *
 * NOTE: the approved V1 taxonomy is 3 Trades / 11 Tasks (4 under MASONRY,
 * 4 under ELECTRICAL, 3 under PLUMBING) — confirmed on CTO review of
 * Patch 1. Earlier scope-document section headers said "12 Tasks"; that was
 * a documentation error, not an omitted task, and has been corrected
 * (see docs/CapabilityModel.md §7). This seed is the authoritative list.
 */
import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

interface TaskSeed {
  code: string;
  name: string;
}

interface TradeSeed {
  code: string;
  name: string;
  tasks: TaskSeed[];
}

export const V1_TAXONOMY: TradeSeed[] = [
  {
    code: 'MASONRY',
    name: 'Masonry',
    tasks: [
      { code: 'BRICKWORK_NEW_WALL', name: 'Brickwork - New Wall' },
      { code: 'BRICKWORK_REPAIR', name: 'Brickwork - Repair' },
      { code: 'BLOCKWORK', name: 'Blockwork' },
      { code: 'PLASTER', name: 'Plaster' },
    ],
  },
  {
    code: 'ELECTRICAL',
    name: 'Electrical',
    tasks: [
      { code: 'FAN_INSTALLATION', name: 'Fan Installation' },
      { code: 'LIGHT_INSTALLATION', name: 'Light Installation' },
      { code: 'WIRING', name: 'Wiring' },
      { code: 'FAULT_FINDING', name: 'Fault Finding' },
    ],
  },
  {
    code: 'PLUMBING',
    name: 'Plumbing',
    tasks: [
      { code: 'LEAKAGE_REPAIR', name: 'Leakage Repair' },
      { code: 'PIPE_INSTALLATION', name: 'Pipe Installation' },
      { code: 'BATHROOM_PLUMBING', name: 'Bathroom Plumbing' },
    ],
  },
];

export async function seedTaxonomy(client: PrismaClient = prisma) {
  let trades = 0;
  let tasks = 0;

  for (const trade of V1_TAXONOMY) {
    const tradeRow = await client.trade.upsert({
      where: { code: trade.code },
      update: { name: trade.name },
      create: { code: trade.code, name: trade.name },
    });
    trades++;

    for (const task of trade.tasks) {
      await client.task.upsert({
        where: { code: task.code },
        update: { name: task.name, tradeId: tradeRow.id },
        create: { code: task.code, name: task.name, tradeId: tradeRow.id },
      });
      tasks++;
    }
  }

  return { trades, tasks };
}

if (require.main === module) {
  seedTaxonomy()
    .then(({ trades, tasks }) => {
      console.log(`Taxonomy seed complete: ${trades} trades, ${tasks} tasks.`);
      return prisma.$disconnect();
    })
    .catch(async (e) => {
      console.error(e);
      await prisma.$disconnect();
      process.exit(1);
    });
}
