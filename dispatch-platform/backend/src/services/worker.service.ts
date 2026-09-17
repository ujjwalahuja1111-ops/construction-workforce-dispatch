import { Shift } from '@prisma/client';
import { prisma } from '../config/prisma';
import { AppError } from '../utils/errors';
import { Role } from '../types/domain';

export interface CompleteWorkerProfileInput {
  fullName: string;
  skills: string[];        // list of skill codes
  experienceYears: number;
  dailyWage: number;
  city: string;
  state: string;
  homeLatitude?: number;
  homeLongitude?: number;
}

export class WorkerService {
  static async me(userId: string) {
    const user = await prisma.user.findUnique({
      where: { id: userId },
      include: { worker: true },
    });
    if (!user || user.role !== Role.WORKER) throw AppError.notFound();
    return { user, worker: user.worker };
  }

  static async completeProfile(userId: string, input: CompleteWorkerProfileInput) {
    const user = await prisma.user.findUnique({
      where: { id: userId },
      include: { worker: true },
    });
    if (!user) throw AppError.notFound();
    if (user.role !== Role.WORKER) throw AppError.forbidden('Not a worker account');

    const skillsCsv = input.skills.join(',');

    const worker = user.worker
      ? await prisma.worker.update({
          where: { userId },
          data: {
            skills: skillsCsv,
            experienceYears: input.experienceYears,
            dailyWage: input.dailyWage,
            city: input.city,
            state: input.state,
            homeLatitude: input.homeLatitude,
            homeLongitude: input.homeLongitude,
          },
        })
      : await prisma.worker.create({
          data: {
            userId,
            skills: skillsCsv,
            experienceYears: input.experienceYears,
            dailyWage: input.dailyWage,
            city: input.city,
            state: input.state,
            homeLatitude: input.homeLatitude,
            homeLongitude: input.homeLongitude,
          },
        });

    await prisma.user.update({
      where: { id: userId },
      data: { fullName: input.fullName },
    });

    return worker;
  }

  static async updateLocation(userId: string, lat: number, lng: number) {
    const worker = await prisma.worker.findUnique({ where: { userId } });
    if (!worker) throw AppError.notFound('Worker profile not found');
    return prisma.worker.update({
      where: { id: worker.id },
      data: { currentLatitude: lat, currentLongitude: lng },
    });
  }

  static async setAvailability(userId: string, available: boolean) {
    const worker = await prisma.worker.findUnique({ where: { userId } });
    if (!worker) throw AppError.notFound('Worker profile not found');
    return prisma.worker.update({
      where: { id: worker.id },
      data: { isAvailable: available },
    });
  }

  static async listPendingOffers(userId: string) {
    const worker = await prisma.worker.findUnique({ where: { userId } });
    if (!worker) throw AppError.notFound('Worker profile not found');
    return prisma.jobOffer.findMany({
      where: {
        workerId: worker.id,
        status: 'PENDING',
        expiresAt: { gt: new Date() },
      },
      include: {
        job: { include: { project: { include: { contractor: true } } } },
      },
      orderBy: { score: 'desc' },
    });
  }

  static async listShiftHistory(userId: string) {
    const worker = await prisma.worker.findUnique({ where: { userId } });
    if (!worker) throw AppError.notFound('Worker profile not found');
    return prisma.shift.findMany({
      where: { workerId: worker.id },
      include: {
        job: { include: { project: { include: { contractor: true } } } },
      },
      orderBy: { shiftDate: 'desc' },
    });
  }

  static async earnings(userId: string) {
    const worker = await prisma.worker.findUnique({ where: { userId } });
    if (!worker) throw AppError.notFound('Worker profile not found');

    const shifts = await prisma.shift.findMany({
      where: { workerId: worker.id, state: { in: ['CLOSED', 'CHECKED_OUT'] } },
      orderBy: { shiftDate: 'desc' },
    });

    const total = shifts.reduce((sum: number, s: Shift) => sum + s.amountEarned, 0);
    const now = new Date();
    const weekStart = new Date(now);
    weekStart.setDate(now.getDate() - 7);
    const monthStart = new Date(now);
    monthStart.setMonth(now.getMonth() - 1);

    const week = shifts
      .filter((s: Shift) => s.shiftDate >= weekStart)
      .reduce((sum: number, s: Shift) => sum + s.amountEarned, 0);
    const month = shifts
      .filter((s: Shift) => s.shiftDate >= monthStart)
      .reduce((sum: number, s: Shift) => sum + s.amountEarned, 0);

    return {
      total,
      week,
      month,
      shifts: shifts.slice(0, 20),
    };
  }
}
