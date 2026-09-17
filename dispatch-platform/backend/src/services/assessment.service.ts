import { z } from 'zod';
import { prisma } from '../config/prisma';
import { AppError } from '../utils/errors';
import { AssessmentType } from '../types/domain';

/**
 * AssessmentService
 *
 * Assessment rows are append-only evidence (Contract §9): this service
 * intentionally exposes no update/delete method. No DB-level immutability
 * trigger was added — SQLite/Prisma have no clean, already-used pattern for
 * that in this codebase (see Contract §9's own "don't over-engineer"
 * guidance) — the append-only guarantee lives here, at the service layer,
 * same as every other invariant in this codebase that isn't a DB
 * constraint.
 */

const TYPE_VALUES = Object.values(AssessmentType) as [string, ...string[]];

export const recordAssessmentSchema = z.object({
  type: z.enum(TYPE_VALUES),
  result: z.string().min(1).max(500),
  assessedBy: z.string().nullable().optional(),
  evidenceNotes: z.string().max(2000).nullable().optional(),
});
export type RecordAssessmentInput = z.infer<typeof recordAssessmentSchema>;

export class AssessmentService {
  static async record(workerCapabilityId: string, rawInput: RecordAssessmentInput) {
    const input = recordAssessmentSchema.parse(rawInput);

    const capability = await prisma.workerCapability.findUnique({
      where: { id: workerCapabilityId },
    });
    if (!capability) throw AppError.notFound('WorkerCapability not found');

    return prisma.assessment.create({
      data: {
        workerCapabilityId,
        type: input.type,
        result: input.result,
        assessedBy: input.assessedBy ?? null,
        evidenceNotes: input.evidenceNotes ?? null,
      },
    });
  }

  static async listForCapability(workerCapabilityId: string) {
    return prisma.assessment.findMany({
      where: { workerCapabilityId },
      orderBy: { assessedAt: 'asc' },
    });
  }
}
