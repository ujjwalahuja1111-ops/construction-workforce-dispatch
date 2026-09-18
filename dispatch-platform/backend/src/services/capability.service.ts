import { z } from 'zod';
import { Prisma } from '@prisma/client';
import { prisma } from '../config/prisma';
import { AppError } from '../utils/errors';
import { CapabilityLevel, CapabilityProvenance, AssessmentType } from '../types/domain';

/**
 * CapabilityService
 *
 * Minimal repository/service support for the Patch 1 / Milestone 0C
 * capability taxonomy (Trade / Task / WorkerCapability). No API route calls
 * into this yet — that's Patch 2 — so this exists purely so the schema has
 * an exercised, testable persistence path and isn't just inert DDL.
 *
 * This layer does NOT touch Worker.skills, Job, JobOffer, Shift, or
 * DispatchEngine, and nothing here is read by dispatch yet.
 */

const LEVEL_VALUES = Object.values(CapabilityLevel);
const PROVENANCE_VALUES = Object.values(CapabilityProvenance) as [string, ...string[]];

// `level`/`provenance` are validated here, at the service boundary — not as
// a DB CHECK constraint or Prisma enum. This matches the existing, accepted
// convention for every other enum-like column in this schema (Job.status,
// Shift.state, JobOffer.status, Rating.score are all plain columns
// validated in application code, never at the DB layer — see
// KnownLimitations.md F2). Introducing the first DB-level enum here would
// be inconsistent with the rest of the codebase for no scoped reason.
export const createCapabilitySchema = z.object({
  workerId: z.string().uuid(),
  taskId: z.string().uuid(),
  level: z.number().int().refine((v) => (LEVEL_VALUES as number[]).includes(v), {
    message: `level must be one of ${LEVEL_VALUES.join(', ')}`,
  }),
  provenance: z.enum(PROVENANCE_VALUES),
  // Deliberately no formula, no default derived from experience/TrustScore —
  // see Contract §6. Nullable/omittable.
  confidence: z.number().min(0).max(1).nullable().optional(),
  restrictions: z.string().nullable().optional(),
  evidenceRef: z.string().nullable().optional(),
  lastVerifiedAt: z.date().nullable().optional(),
});
export type CreateCapabilityInput = z.infer<typeof createCapabilitySchema>;

// Patch 2 — Worker Capability API (Self-Declaration). Deliberately a
// separate, narrower schema from `createCapabilitySchema` above: it has no
// `workerId` and no `provenance` field at all, so there is no input path by
// which a client could ever supply either — not a validation rule against
// it, a structural absence. See the Patch 2 contract §4/§6.
export const selfDeclareCapabilitySchema = z.object({
  taskId: z.string().uuid(),
  level: z.number().int().refine((v) => (LEVEL_VALUES as number[]).includes(v), {
    message: `level must be one of ${LEVEL_VALUES.join(', ')}`,
  }),
});
export type SelfDeclareCapabilityInput = z.infer<typeof selfDeclareCapabilitySchema>;

export class CapabilityService {
  // ---------------------------------------------------------------------
  // Trade / Task (read-only in this patch — the taxonomy is seed-managed)
  // ---------------------------------------------------------------------

  static async listActiveTrades() {
    return prisma.trade.findMany({ where: { isActive: true }, orderBy: { code: 'asc' } });
  }

  static async getTradeByCode(code: string) {
    const trade = await prisma.trade.findUnique({ where: { code } });
    if (!trade) throw AppError.notFound('Trade not found');
    return trade;
  }

  static async listTasksByTrade(tradeId: string) {
    return prisma.task.findMany({ where: { tradeId, isActive: true }, orderBy: { code: 'asc' } });
  }

  static async getTaskByCode(code: string) {
    const task = await prisma.task.findUnique({ where: { code } });
    if (!task) throw AppError.notFound('Task not found');
    return task;
  }

  // ---------------------------------------------------------------------
  // WorkerCapability
  // ---------------------------------------------------------------------

  static async createCapability(rawInput: CreateCapabilityInput) {
    const input = createCapabilitySchema.parse(rawInput);

    const [worker, task] = await Promise.all([
      prisma.worker.findUnique({ where: { id: input.workerId } }),
      prisma.task.findUnique({ where: { id: input.taskId } }),
    ]);
    if (!worker) throw AppError.notFound('Worker not found');
    if (!task) throw AppError.notFound('Task not found');

    const existing = await prisma.workerCapability.findUnique({
      where: { workerId_taskId: { workerId: input.workerId, taskId: input.taskId } },
    });
    if (existing) {
      throw AppError.conflict('A WorkerCapability already exists for this worker/task pair');
    }

    return prisma.workerCapability.create({
      data: {
        workerId: input.workerId,
        taskId: input.taskId,
        level: input.level,
        provenance: input.provenance,
        confidence: input.confidence ?? null,
        restrictions: input.restrictions ?? null,
        evidenceRef: input.evidenceRef ?? null,
        lastVerifiedAt: input.lastVerifiedAt ?? null,
      },
    });
  }

  static async getCapability(workerId: string, taskId: string) {
    const capability = await prisma.workerCapability.findUnique({
      where: { workerId_taskId: { workerId, taskId } },
    });
    if (!capability) throw AppError.notFound('WorkerCapability not found');
    return capability;
  }

  static async listCapabilitiesForWorker(workerId: string) {
    // NOTE (Patch 2): widened from `include: { task: true }` to also nest
    // `task.trade`, so the Patch 2 GET /api/worker/capabilities response can
    // include `task.tradeCode` per the approved contract §3, without a
    // second query. Purely additive to the shape of what's returned — the
    // existing Patch 1 test that reads `capabilities[0].task.code` is
    // unaffected, and no existing caller reads less than it did before.
    return prisma.workerCapability.findMany({
      where: { workerId },
      include: { task: { include: { trade: true } } },
      orderBy: { createdAt: 'asc' },
    });
  }

  // ---------------------------------------------------------------------
  // Patch 2 — Worker Capability API (Self-Declaration)
  // ---------------------------------------------------------------------

  /**
   * Worker self-declaration entry point. Always writes
   * `provenance = SELF_DECLARED` — the input type has no `provenance` field,
   * so there is no path by which a caller could set anything else.
   *
   * Three deterministic outcomes, keyed only on the EXISTING row's
   * provenance (never on request order or timing) — see Patch 2 contract
   * §7/§8 for the full reasoning:
   *
   *   1. No existing row              -> create (SELF_DECLARED) + an
   *      Assessment(SELF_DECLARATION) row. Returns `created: true`.
   *   2. Existing, still SELF_DECLARED -> update `level` in place on the
   *      SAME row + append a new Assessment(SELF_DECLARATION) row (full
   *      history is preserved via Assessment even though WorkerCapability
   *      only ever shows the latest value — same denormalized-current-value
   *      /append-only-log split already used by `Worker.avgRating` +
   *      `Rating`, and `Worker.trustScore` + the shift/rating history
   *      TrustEngine reads). Returns `created: false`.
   *   3. Existing, provenance beyond SELF_DECLARED -> reject. Nothing is
   *      written — not the WorkerCapability row, not even an Assessment
   *      row. This is the only place provenance accuracy is protected;
   *      case 2's in-place update is safe precisely because it can only
   *      ever run when nothing has been verified yet.
   */
  static async selfDeclare(workerUserId: string, rawInput: SelfDeclareCapabilityInput) {
    const input = selfDeclareCapabilitySchema.parse(rawInput);

    const worker = await prisma.worker.findUnique({ where: { userId: workerUserId } });
    if (!worker) throw AppError.notFound('Worker profile not found');

    const task = await prisma.task.findUnique({ where: { id: input.taskId } });
    if (!task || !task.isActive) throw AppError.notFound('Task not found');

    const existing = await prisma.workerCapability.findUnique({
      where: { workerId_taskId: { workerId: worker.id, taskId: input.taskId } },
    });

    if (existing && existing.provenance !== CapabilityProvenance.SELF_DECLARED) {
      throw AppError.conflict(
        'This capability has already been assessed and cannot be changed by self-declaration',
      );
    }

    const includeTaskTrade = { task: { include: { trade: true } } } as const;

    if (existing) {
      const capability = await prisma.$transaction(async (tx: Prisma.TransactionClient) => {
        const updated = await tx.workerCapability.update({
          where: { id: existing.id },
          data: { level: input.level },
          include: includeTaskTrade,
        });
        await tx.assessment.create({
          data: {
            workerCapabilityId: updated.id,
            type: AssessmentType.SELF_DECLARATION,
            result: `Self-declared level changed ${existing.level} → ${input.level}`,
          },
        });
        return updated;
      });
      return { capability, created: false as const };
    }

    const capability = await prisma.$transaction(async (tx: Prisma.TransactionClient) => {
      const created = await tx.workerCapability.create({
        data: {
          workerId: worker.id,
          taskId: input.taskId,
          level: input.level,
          provenance: CapabilityProvenance.SELF_DECLARED,
        },
        include: includeTaskTrade,
      });
      await tx.assessment.create({
        data: {
          workerCapabilityId: created.id,
          type: AssessmentType.SELF_DECLARATION,
          result: `Self-declared level ${input.level}`,
        },
      });
      return created;
    });
    return { capability, created: true as const };
  }

  /**
   * GET /api/worker/capabilities — resolves the Worker row from the JWT
   * subject the same way `WorkerService.me`/`completeProfile` do, then
   * delegates to `listCapabilitiesForWorker`. No other caller can reach
   * another worker's rows through this method — there is no workerId
   * parameter here at all, only the authenticated user's own id.
   */
  static async listForAuthenticatedWorker(workerUserId: string) {
    const worker = await prisma.worker.findUnique({ where: { userId: workerUserId } });
    if (!worker) throw AppError.notFound('Worker profile not found');
    return this.listCapabilitiesForWorker(worker.id);
  }
}
