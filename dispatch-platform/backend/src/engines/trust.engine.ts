import { prisma } from '../config/prisma';
import { clamp } from '../utils/geo';

/**
 * TrustEngine - recomputes a worker's trust score (0..100).
 *
 * Weighted blend of:
 *   - attendance:  completed / total          × 40
 *   - acceptance:  accepted / (accepted+declined) × 25
 *   - reliability: 1 - (cancelled / total)    × 20
 *   - rating:      avgRating / 5              × 15
 *
 * New workers (0 shifts) default to a base of 70 so cold-starts still get
 * dispatched. Score is persisted on the Worker row.
 */
export class TrustEngine {
  static async recompute(workerId: string): Promise<number> {
    const w = await prisma.worker.findUnique({ where: { id: workerId } });
    if (!w) return 0;

    if (w.totalShifts === 0) {
      // cold-start baseline
      await prisma.worker.update({
        where: { id: workerId },
        data: { trustScore: 70 },
      });
      return 70;
    }

    const attendance = w.completedShifts / w.totalShifts;
    const offersTotal = w.acceptedOffers + w.declinedOffers;
    const acceptance = offersTotal === 0 ? 0.5 : w.acceptedOffers / offersTotal;
    const reliability = 1 - w.cancelledShifts / w.totalShifts;
    const rating = (w.avgRating || 0) / 5;

    const raw =
      attendance * 40 + acceptance * 25 + reliability * 20 + rating * 15;

    const score = Math.round(clamp(raw, 0, 100));
    await prisma.worker.update({
      where: { id: workerId },
      data: { trustScore: score },
    });
    return score;
  }
}
