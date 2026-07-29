import { prisma } from '../config/prisma';
import { AppError } from '../utils/errors';
import { JobStatus, OfferStatus, ShiftState } from '../types/domain';
import { DispatchEngine } from '../engines/dispatch.engine';
import { TrustEngine } from '../engines/trust.engine';

export interface CreateJobInput {
  projectId: string;
  skill: string;
  headcount: number;
  dailyWage: number;
  shiftDate: string;    // ISO
  startTime: string;    // "HH:mm"
  endTime: string;      // "HH:mm"
  notes?: string;
}

export class JobService {
  static async createAndDispatch(contractorUserId: string, input: CreateJobInput) {
    const contractor = await prisma.contractor.findUnique({
      where: { userId: contractorUserId },
    });
    if (!contractor) throw AppError.notFound('Contractor profile not found');

    const project = await prisma.project.findUnique({
      where: { id: input.projectId },
    });
    if (!project || project.contractorId !== contractor.id) {
      throw AppError.forbidden('Project not owned by this contractor');
    }

    const job = await prisma.job.create({
      data: {
        projectId: input.projectId,
        skill: input.skill,
        headcount: input.headcount,
        dailyWage: input.dailyWage,
        shiftDate: new Date(input.shiftDate),
        startTime: input.startTime,
        endTime: input.endTime,
        notes: input.notes,
        status: JobStatus.OPEN,
      },
    });

    const dispatch = await DispatchEngine.dispatchJob(job.id);
    return { job, dispatch };
  }

  static async acceptOffer(workerUserId: string, offerId: string) {
    const worker = await prisma.worker.findUnique({ where: { userId: workerUserId } });
    if (!worker) throw AppError.notFound('Worker profile not found');

    const offer = await prisma.jobOffer.findUnique({
      where: { id: offerId },
      include: { job: true },
    });
    if (!offer) throw AppError.notFound('Offer not found');
    if (offer.workerId !== worker.id) throw AppError.forbidden();
    if (offer.status !== OfferStatus.PENDING) {
      throw AppError.invalidState(`Offer already ${offer.status}`);
    }
    if (offer.expiresAt < new Date()) {
      await prisma.jobOffer.update({
        where: { id: offer.id },
        data: { status: OfferStatus.EXPIRED },
      });
      throw AppError.invalidState('Offer expired');
    }

    // Reject if job already full
    const filled = await prisma.shift.count({ where: { jobId: offer.jobId } });
    if (filled >= offer.job.headcount) {
      await prisma.jobOffer.update({
        where: { id: offer.id },
        data: { status: OfferStatus.EXPIRED },
      });
      throw AppError.conflict('Job is already fully staffed');
    }

    const result = await prisma.$transaction(async (tx) => {
      // Auto-decline any other pending offers for this worker on same job (defense-in-depth)
      await tx.jobOffer.updateMany({
        where: {
          workerId: worker.id,
          jobId: offer.jobId,
          status: OfferStatus.PENDING,
          id: { not: offer.id },
        },
        data: { status: OfferStatus.DECLINED },
      });

      const updatedOffer = await tx.jobOffer.update({
        where: { id: offer.id },
        data: { status: OfferStatus.ACCEPTED, respondedAt: new Date() },
      });

      const shift = await tx.shift.create({
        data: {
          jobId: offer.jobId,
          workerId: worker.id,
          state: ShiftState.ACCEPTED,
          shiftDate: offer.job.shiftDate,
          scheduledStart: offer.job.startTime,
          scheduledEnd: offer.job.endTime,
          wageAmount: offer.job.dailyWage,
        },
      });

      await tx.shiftEvent.create({
        data: {
          shiftId: shift.id,
          fromState: ShiftState.OFFERED,
          toState: ShiftState.ACCEPTED,
          note: 'Worker accepted offer',
        },
      });

      await tx.worker.update({
        where: { id: worker.id },
        data: {
          acceptedOffers: { increment: 1 },
          totalShifts: { increment: 1 },
        },
      });

      return { updatedOffer, shift };
    });

    // Fulfil job if headcount met
    const newlyFilled = filled + 1;
    if (newlyFilled >= offer.job.headcount) {
      await prisma.job.update({
        where: { id: offer.jobId },
        data: { status: JobStatus.FULFILLED },
      });
      await prisma.jobOffer.updateMany({
        where: { jobId: offer.jobId, status: OfferStatus.PENDING },
        data: { status: OfferStatus.EXPIRED },
      });
    }

    await TrustEngine.recompute(worker.id);
    return { shift: result.shift, offer: result.updatedOffer };
  }

  static async declineOffer(workerUserId: string, offerId: string) {
    const worker = await prisma.worker.findUnique({ where: { userId: workerUserId } });
    if (!worker) throw AppError.notFound('Worker profile not found');
    const offer = await prisma.jobOffer.findUnique({ where: { id: offerId } });
    if (!offer || offer.workerId !== worker.id) throw AppError.notFound();
    if (offer.status !== OfferStatus.PENDING) {
      throw AppError.invalidState(`Offer already ${offer.status}`);
    }

    const updated = await prisma.jobOffer.update({
      where: { id: offer.id },
      data: { status: OfferStatus.DECLINED, respondedAt: new Date() },
    });
    await prisma.worker.update({
      where: { id: worker.id },
      data: { declinedOffers: { increment: 1 } },
    });
    await TrustEngine.recompute(worker.id);
    return updated;
  }
}
