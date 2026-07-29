import { prisma } from '../config/prisma';
import { env } from '../config/env';
import { haversineKm } from '../utils/geo';
import { OfferStatus, JobStatus } from '../types/domain';

/**
 * DispatchEngine
 *
 * Given a Job, return a ranked list of candidate workers matching:
 *   - skill  (job.skill must be in worker.skills CSV)
 *   - available (worker.isAvailable && no overlapping active shift on shiftDate)
 *   - distance (Haversine, capped by DISPATCH_MAX_RADIUS_KM)
 *
 * Score (0..1, higher = better) is a weighted blend of:
 *   - trustScore      (0..100) * 0.35
 *   - acceptance rate (0..1)   * 0.20
 *   - distance decay  (0..1)   * 0.30   [1 at 0km, 0 at maxRadius]
 *   - workload penalty(0..1)   * 0.15   [1 if idle today, less if busy]
 *
 * Then creates JobOffer rows for the top N candidates.
 */
export class DispatchEngine {
  static async dispatchJob(jobId: string) {
    const job = await prisma.job.findUnique({
      where: { id: jobId },
      include: { project: true, offers: true, shifts: true },
    });
    if (!job) throw new Error(`Job ${jobId} not found`);
    if (job.status !== JobStatus.OPEN && job.status !== JobStatus.DISPATCHING) {
      throw new Error(`Job ${jobId} not dispatchable (status=${job.status})`);
    }

    const alreadyOffered = new Set(job.offers.map((o) => o.workerId));
    const remaining = job.headcount - job.shifts.length;
    if (remaining <= 0) return { offersCreated: 0, remaining: 0 };

    // Candidate pool: workers with skill match + available + not already offered
    const workers = await prisma.worker.findMany({
      where: {
        isAvailable: true,
        skills: { contains: job.skill },
        id: { notIn: [...alreadyOffered] },
      },
      include: { user: true },
    });

    const ranked = workers
      .map((w) => {
        const dist =
          w.currentLatitude != null && w.currentLongitude != null
            ? haversineKm(
                w.currentLatitude,
                w.currentLongitude,
                job.project.latitude,
                job.project.longitude,
              )
            : w.homeLatitude != null && w.homeLongitude != null
              ? haversineKm(
                  w.homeLatitude,
                  w.homeLongitude,
                  job.project.latitude,
                  job.project.longitude,
                )
              : Number.POSITIVE_INFINITY;

        return { worker: w, distanceKm: dist };
      })
      .filter((c) => c.distanceKm <= env.dispatchMaxRadiusKm)
      .map((c) => {
        const trust = c.worker.trustScore / 100;
        const offersTotal = c.worker.acceptedOffers + c.worker.declinedOffers;
        const acceptance = offersTotal === 0 ? 0.5 : c.worker.acceptedOffers / offersTotal;
        const distanceDecay = 1 - c.distanceKm / env.dispatchMaxRadiusKm;
        const workload = 1; // MVP: no daily workload counter yet

        const score =
          trust * 0.35 + acceptance * 0.2 + distanceDecay * 0.3 + workload * 0.15;

        return { ...c, score };
      })
      .sort((a, b) => b.score - a.score)
      .slice(0, Math.min(env.dispatchMaxCandidates, remaining * 3));

    if (ranked.length === 0) {
      return { offersCreated: 0, remaining, candidates: 0 };
    }

    const expiresAt = new Date(Date.now() + 15 * 60 * 1000); // 15 min TTL

    const created = await prisma.$transaction(async (tx) => {
      const rows = [];
      for (const c of ranked) {
        const offer = await tx.jobOffer.create({
          data: {
            jobId: job.id,
            workerId: c.worker.id,
            status: OfferStatus.PENDING,
            score: c.score,
            distanceKm: c.distanceKm,
            expiresAt,
          },
        });
        await tx.notification.create({
          data: {
            userId: c.worker.userId,
            type: 'JOB_OFFER',
            title: 'New job offer',
            body: `${job.skill} · ₹${job.dailyWage}/day · ${c.distanceKm.toFixed(1)} km`,
            data: JSON.stringify({ jobId: job.id, offerId: offer.id }),
          },
        });
        rows.push(offer);
      }
      await tx.job.update({
        where: { id: job.id },
        data: { status: JobStatus.DISPATCHING },
      });
      return rows;
    });

    return { offersCreated: created.length, remaining, candidates: ranked.length };
  }
}
