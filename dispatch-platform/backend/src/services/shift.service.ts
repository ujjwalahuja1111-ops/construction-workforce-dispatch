import { prisma } from '../config/prisma';
import { AppError } from '../utils/errors';
import { ShiftEngine } from '../engines/shift.engine';
import { ShiftState, ShiftStateT } from '../types/domain';
import { haversineKm, hhmmToMinutes } from '../utils/geo';
import { TrustEngine } from '../engines/trust.engine';

const CHECKIN_MAX_KM = 0.5; // 500m geofence around site

export class ShiftService {
  static async get(shiftId: string, workerUserId: string) {
    const shift = await prisma.shift.findUnique({
      where: { id: shiftId },
      include: {
        worker: true,
        job: { include: { project: { include: { contractor: true } } } },
        events: { orderBy: { createdAt: 'asc' } },
      },
    });
    if (!shift) throw AppError.notFound();
    if (shift.worker.userId !== workerUserId) throw AppError.forbidden();
    return shift;
  }

  static async currentActive(workerUserId: string) {
    const worker = await prisma.worker.findUnique({ where: { userId: workerUserId } });
    if (!worker) throw AppError.notFound('Worker profile not found');
    return prisma.shift.findFirst({
      where: {
        workerId: worker.id,
        state: {
          in: [
            'ACCEPTED',
            'TRAVELLING',
            'ARRIVED',
            'CHECKED_IN',
            'WORKING',
            'BREAK',
            'RESUMED',
            'COMPLETED',
            'CHECKED_OUT',
          ],
        },
      },
      include: {
        job: { include: { project: { include: { contractor: true } } } },
        events: { orderBy: { createdAt: 'asc' } },
      },
      orderBy: { shiftDate: 'asc' },
    });
  }

  private static async transition(
    shiftId: string,
    workerUserId: string,
    to: ShiftStateT,
    opts: { lat?: number; lng?: number; note?: string } = {},
  ) {
    const shift = await this.get(shiftId, workerUserId);
    const from = shift.state as ShiftStateT;
    ShiftEngine.assertTransition(from, to);

    const updated = await prisma.$transaction(async (tx) => {
      const patch: Record<string, unknown> = { state: to };

      if (to === ShiftState.CHECKED_IN) {
        // Attendance validation: must be within geofence
        const proj = shift.job.project;
        if (opts.lat == null || opts.lng == null) {
          throw AppError.badRequest('Check-in requires GPS location');
        }
        const dist = haversineKm(opts.lat, opts.lng, proj.latitude, proj.longitude);
        if (dist > CHECKIN_MAX_KM) {
          throw AppError.invalidState(
            `Too far from site (${(dist * 1000).toFixed(0)}m). Must be within ${CHECKIN_MAX_KM * 1000}m.`,
          );
        }
        const scheduled = hhmmToMinutes(shift.scheduledStart);
        const nowMin = new Date().getHours() * 60 + new Date().getMinutes();
        const late = Math.max(0, nowMin - scheduled);
        patch.checkInAt = new Date();
        patch.checkInLat = opts.lat;
        patch.checkInLng = opts.lng;
        patch.lateMinutes = late;
      }

      if (to === ShiftState.CHECKED_OUT) {
        if (opts.lat == null || opts.lng == null) {
          throw AppError.badRequest('Check-out requires GPS location');
        }
        patch.checkOutAt = new Date();
        patch.checkOutLat = opts.lat;
        patch.checkOutLng = opts.lng;

        const scheduledEnd = hhmmToMinutes(shift.scheduledEnd);
        const nowMin = new Date().getHours() * 60 + new Date().getMinutes();
        const earlyExit = Math.max(0, scheduledEnd - nowMin);
        patch.earlyExitMinutes = earlyExit;

        if (shift.checkInAt) {
          const worked = Math.round(
            (Date.now() - new Date(shift.checkInAt).getTime()) / 60000,
          );
          patch.workedMinutes = worked;
        }
      }

      if (to === ShiftState.CLOSED) {
        // Finalize pay proportional to worked/scheduled
        const scheduled =
          hhmmToMinutes(shift.scheduledEnd) - hhmmToMinutes(shift.scheduledStart);
        const worked = (shift.workedMinutes || 0);
        const ratio = scheduled > 0 ? Math.min(1, worked / scheduled) : 1;
        const amount = Math.round(shift.wageAmount * ratio);
        patch.amountEarned = amount;

        await tx.worker.update({
          where: { id: shift.workerId },
          data: {
            completedShifts: { increment: 1 },
            totalEarnings: { increment: amount },
          },
        });
      }

      const s = await tx.shift.update({ where: { id: shift.id }, data: patch });
      await tx.shiftEvent.create({
        data: {
          shiftId: shift.id,
          fromState: from,
          toState: to,
          latitude: opts.lat,
          longitude: opts.lng,
          note: opts.note,
        },
      });
      await tx.notification.create({
        data: {
          userId: workerUserId,
          type: 'SHIFT_UPDATE',
          title: `Shift ${to.toLowerCase().replace('_', ' ')}`,
          body: `Your shift moved to ${to}`,
          data: JSON.stringify({ shiftId: shift.id }),
        },
      });
      return s;
    });

    if (to === ShiftState.CLOSED) {
      await TrustEngine.recompute(shift.workerId);
    }
    return updated;
  }

  static travel(shiftId: string, userId: string, lat?: number, lng?: number) {
    return this.transition(shiftId, userId, ShiftState.TRAVELLING, { lat, lng });
  }
  static arrive(shiftId: string, userId: string, lat?: number, lng?: number) {
    return this.transition(shiftId, userId, ShiftState.ARRIVED, { lat, lng });
  }
  static checkIn(shiftId: string, userId: string, lat: number, lng: number) {
    return this.transition(shiftId, userId, ShiftState.CHECKED_IN, { lat, lng });
  }
  static startWork(shiftId: string, userId: string) {
    return this.transition(shiftId, userId, ShiftState.WORKING);
  }
  static startBreak(shiftId: string, userId: string) {
    return this.transition(shiftId, userId, ShiftState.BREAK);
  }
  static resume(shiftId: string, userId: string) {
    return this.transition(shiftId, userId, ShiftState.RESUMED);
  }
  static complete(shiftId: string, userId: string) {
    return this.transition(shiftId, userId, ShiftState.COMPLETED);
  }
  static checkOut(shiftId: string, userId: string, lat: number, lng: number) {
    return this.transition(shiftId, userId, ShiftState.CHECKED_OUT, { lat, lng });
  }
  static close(shiftId: string, userId: string) {
    return this.transition(shiftId, userId, ShiftState.CLOSED);
  }
}
