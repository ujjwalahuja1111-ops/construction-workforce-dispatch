/**
 * Seed script - generates a realistic dataset for local development.
 *
 * Volume (Phase 1 request):
 *   - 2 admins, 5 contractors, 10 workers
 *   - 5 projects, ~10 jobs (mix of OPEN/DISPATCHING/FULFILLED)
 *   - ~15 offers, ~10 shifts across lifecycle states
 *
 * All accounts share the dev OTP: 123456.
 */
import { PrismaClient } from '@prisma/client';
import { randomUUID } from 'crypto';
import { seedTaxonomy } from './seeds/taxonomy';

const prisma = new PrismaClient();

// Bangalore + Mumbai + Delhi anchor coordinates
const CITIES = [
  { city: 'Bengaluru', state: 'Karnataka', lat: 12.9716, lng: 77.5946 },
  { city: 'Mumbai',    state: 'Maharashtra', lat: 19.0760, lng: 72.8777 },
  { city: 'Delhi',     state: 'Delhi',       lat: 28.6139, lng: 77.2090 },
];

const SKILLS = ['MASON','HELPER','BAR_BENDER','CARPENTER','PAINTER','ELECTRICIAN','PLUMBER','WELDER','TILE_LAYER','SUPERVISOR'];

function jitter(base: number, kmSpread = 8): number {
  // ~1km ≈ 0.009° at these latitudes; produce a small random offset
  const deg = (kmSpread / 111) * (Math.random() - 0.5) * 2;
  return base + deg;
}

function pick<T>(arr: T[]): T { return arr[Math.floor(Math.random() * arr.length)]; }
function pickN<T>(arr: T[], n: number): T[] {
  const copy = [...arr].sort(() => Math.random() - 0.5);
  return copy.slice(0, n);
}

async function main() {
  console.log('Seeding database...');

  // Patch 1 / Milestone 0C capability taxonomy — upsert-idempotent, and
  // deliberately NOT part of the destructive delete-then-recreate block
  // below (that block only ever touches the legacy tables it always has).
  const taxonomy = await seedTaxonomy(prisma);
  console.log(`Capability taxonomy: ${taxonomy.trades} trades, ${taxonomy.tasks} tasks.`);

  // Clear existing (idempotent)
  await prisma.shiftEvent.deleteMany();
  await prisma.rating.deleteMany();
  await prisma.shift.deleteMany();
  await prisma.jobOffer.deleteMany();
  await prisma.job.deleteMany();
  await prisma.project.deleteMany();
  await prisma.notification.deleteMany();
  await prisma.otp.deleteMany();
  await prisma.worker.deleteMany();
  await prisma.contractor.deleteMany();
  await prisma.user.deleteMany();

  // -------------------------------------------------------------------------
  // Admins (2)
  // -------------------------------------------------------------------------
  const adminA = await prisma.user.create({
    data: { phone: '+919000000001', role: 'ADMIN', fullName: 'Admin One', isVerified: true },
  });
  const adminB = await prisma.user.create({
    data: { phone: '+919000000002', role: 'ADMIN', fullName: 'Admin Two', isVerified: true },
  });

  // -------------------------------------------------------------------------
  // Contractors (5)
  // -------------------------------------------------------------------------
  const contractorSeeds = [
    { name: 'Sharma Constructions', company: 'Sharma Constructions Pvt Ltd', city: CITIES[0] },
    { name: 'Mehta Builders',       company: 'Mehta Builders LLP',           city: CITIES[0] },
    { name: 'Rao Infra',            company: 'Rao Infra Services',           city: CITIES[1] },
    { name: 'Iyer Projects',        company: 'Iyer Projects Pvt Ltd',        city: CITIES[1] },
    { name: 'Kapoor Developers',    company: 'Kapoor Developers Ltd',        city: CITIES[2] },
  ];

  const contractors = await Promise.all(
    contractorSeeds.map(async (s, i) => {
      const u = await prisma.user.create({
        data: {
          phone: `+91901000000${i + 1}`,
          role: 'CONTRACTOR',
          fullName: s.name,
          isVerified: true,
        },
      });
      const c = await prisma.contractor.create({
        data: {
          userId: u.id,
          companyName: s.company,
          city: s.city.city,
          state: s.city.state,
          gstNumber: `29ABCDE${1000 + i}F1Z5`,
          rating: 4 + Math.random(),
        },
      });
      return { user: u, contractor: c, city: s.city };
    }),
  );

  // -------------------------------------------------------------------------
  // Workers (10)
  // -------------------------------------------------------------------------
  const workerNames = [
    'Rajesh Kumar', 'Suresh Yadav', 'Anil Patel', 'Vikas Singh', 'Ramesh Verma',
    'Mahesh Sharma', 'Deepak Reddy', 'Sanjay Naidu', 'Manoj Das', 'Pradeep Rao',
  ];

  const workers = await Promise.all(
    workerNames.map(async (name, i) => {
      const city = CITIES[i % CITIES.length];
      const u = await prisma.user.create({
        data: {
          phone: `+91902000${(1000 + i).toString().padStart(4, '0')}`,
          role: 'WORKER',
          fullName: name,
          isVerified: true,
        },
      });
      const skills = pickN(SKILLS, 1 + Math.floor(Math.random() * 3));
      const w = await prisma.worker.create({
        data: {
          userId: u.id,
          skills: skills.join(','),
          experienceYears: 1 + Math.floor(Math.random() * 15),
          dailyWage: 500 + Math.floor(Math.random() * 900),
          city: city.city,
          state: city.state,
          homeLatitude: jitter(city.lat, 5),
          homeLongitude: jitter(city.lng, 5),
          currentLatitude: jitter(city.lat, 3),
          currentLongitude: jitter(city.lng, 3),
          isAvailable: true,
          trustScore: 60 + Math.floor(Math.random() * 35),
          totalShifts: Math.floor(Math.random() * 20),
          completedShifts: 0,
          cancelledShifts: 0,
          acceptedOffers: Math.floor(Math.random() * 25),
          declinedOffers: Math.floor(Math.random() * 5),
          avgRating: 3.5 + Math.random() * 1.5,
          totalEarnings: Math.floor(Math.random() * 50000),
        },
      });
      // Fix internal counters
      await prisma.worker.update({
        where: { id: w.id },
        data: { completedShifts: Math.floor(w.totalShifts * 0.8) },
      });
      return { user: u, worker: w, city };
    }),
  );

  // -------------------------------------------------------------------------
  // Projects (5)
  // -------------------------------------------------------------------------
  const projectSeeds = [
    { name: 'Whitefield Tower A',  ci: 0, addr: 'ITPL Main Road, Whitefield' },
    { name: 'HSR Villa Complex',   ci: 0, addr: 'HSR Layout Sector 3' },
    { name: 'Andheri Metro Yard',  ci: 2, addr: 'Andheri West' },
    { name: 'Bandra Sea Vista',    ci: 3, addr: 'Bandra Reclamation' },
    { name: 'Gurgaon Business Park', ci: 4, addr: 'Sector 44, Gurgaon' },
  ];
  const projects = await Promise.all(
    projectSeeds.map(async (p) => {
      const c = contractors[p.ci];
      return prisma.project.create({
        data: {
          contractorId: c.contractor.id,
          name: p.name,
          siteAddress: p.addr,
          city: c.city.city,
          state: c.city.state,
          latitude: jitter(c.city.lat, 2),
          longitude: jitter(c.city.lng, 2),
          startsOn: new Date(Date.now() - 30 * 86400_000),
          endsOn: new Date(Date.now() + 90 * 86400_000),
          status: 'ACTIVE',
        },
      });
    }),
  );

  // -------------------------------------------------------------------------
  // Jobs (~10)
  // -------------------------------------------------------------------------
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const jobSeeds = [
    { pi: 0, skill: 'MASON',       heads: 3, wage: 850, dayOffset: 0 },
    { pi: 0, skill: 'HELPER',      heads: 5, wage: 550, dayOffset: 0 },
    { pi: 1, skill: 'BAR_BENDER',  heads: 2, wage: 900, dayOffset: 1 },
    { pi: 1, skill: 'CARPENTER',   heads: 2, wage: 950, dayOffset: 2 },
    { pi: 2, skill: 'WELDER',      heads: 2, wage: 1100, dayOffset: 0 },
    { pi: 2, skill: 'HELPER',      heads: 4, wage: 550, dayOffset: 1 },
    { pi: 3, skill: 'PAINTER',     heads: 3, wage: 750, dayOffset: 0 },
    { pi: 3, skill: 'ELECTRICIAN', heads: 1, wage: 1200, dayOffset: 3 },
    { pi: 4, skill: 'PLUMBER',     heads: 2, wage: 1000, dayOffset: 1 },
    { pi: 4, skill: 'TILE_LAYER',  heads: 2, wage: 850, dayOffset: 2 },
  ];

  const jobs = [] as any[];
  for (const j of jobSeeds) {
    const shiftDate = new Date(today);
    shiftDate.setDate(shiftDate.getDate() + j.dayOffset);
    const job = await prisma.job.create({
      data: {
        projectId: projects[j.pi].id,
        skill: j.skill,
        headcount: j.heads,
        dailyWage: j.wage,
        shiftDate,
        startTime: '08:00',
        endTime: '18:00',
        status: 'OPEN',
        notes: `Bring PPE. Skill: ${j.skill}`,
      },
    });
    jobs.push(job);
  }

  // -------------------------------------------------------------------------
  // Offers: create a few pending offers so mobile UI has data on first login
  // -------------------------------------------------------------------------
  // Give worker[0] (Rajesh Kumar) 3 offers from Bangalore jobs.
  const rajesh = workers[0].worker;
  const bengaluruJobs = jobs.filter((j) => {
    const proj = projects.find((p) => p.id === j.projectId)!;
    return proj.city === 'Bengaluru';
  }).slice(0, 3);

  for (const job of bengaluruJobs) {
    await prisma.jobOffer.create({
      data: {
        jobId: job.id,
        workerId: rajesh.id,
        status: 'PENDING',
        score: 0.6 + Math.random() * 0.4,
        distanceKm: 1 + Math.random() * 10,
        expiresAt: new Date(Date.now() + 60 * 60_000),
      },
    });
    await prisma.notification.create({
      data: {
        userId: workers[0].user.id,
        type: 'JOB_OFFER',
        title: 'New job offer',
        body: `${job.skill} · ₹${job.dailyWage}/day`,
        data: JSON.stringify({ jobId: job.id }),
      },
    });
  }

  // Give worker[1] 1 completed shift so history/earnings screens have data
  const suresh = workers[1].worker;
  const sureshJob = jobs[0];
  const closedShift = await prisma.shift.create({
    data: {
      jobId: sureshJob.id,
      workerId: suresh.id,
      state: 'CLOSED',
      shiftDate: new Date(Date.now() - 2 * 86400_000),
      scheduledStart: '08:00',
      scheduledEnd: '18:00',
      wageAmount: sureshJob.dailyWage,
      checkInAt: new Date(Date.now() - 2 * 86400_000 + 8 * 3600_000),
      checkOutAt: new Date(Date.now() - 2 * 86400_000 + 18 * 3600_000),
      workedMinutes: 600,
      amountEarned: sureshJob.dailyWage,
    },
  });
  await prisma.shiftEvent.createMany({
    data: [
      { shiftId: closedShift.id, fromState: 'OFFERED',     toState: 'ACCEPTED' },
      { shiftId: closedShift.id, fromState: 'ACCEPTED',    toState: 'TRAVELLING' },
      { shiftId: closedShift.id, fromState: 'TRAVELLING',  toState: 'ARRIVED' },
      { shiftId: closedShift.id, fromState: 'ARRIVED',     toState: 'CHECKED_IN' },
      { shiftId: closedShift.id, fromState: 'CHECKED_IN',  toState: 'WORKING' },
      { shiftId: closedShift.id, fromState: 'WORKING',     toState: 'COMPLETED' },
      { shiftId: closedShift.id, fromState: 'COMPLETED',   toState: 'CHECKED_OUT' },
      { shiftId: closedShift.id, fromState: 'CHECKED_OUT', toState: 'CLOSED' },
    ],
  });
  await prisma.worker.update({
    where: { id: suresh.id },
    data: { totalEarnings: { increment: sureshJob.dailyWage }, completedShifts: { increment: 1 } },
  });

  console.log(`
Seed complete.

  Admins:       2
  Contractors:  ${contractors.length}
  Workers:      ${workers.length}
  Projects:     ${projects.length}
  Jobs:         ${jobs.length}

  Dev OTP: 123456 (any phone in the DB, or self-register new worker)

Test worker (has 3 pending offers): +919020001000  (${workers[0].user.fullName})
Test worker (has 1 closed shift):   +919020001001  (${workers[1].user.fullName})
Test contractor:                    +919010000001  (${contractors[0].contractor.companyName})
Test admin:                         +919000000001

`);
}

main()
  .then(() => prisma.$disconnect())
  .catch(async (e) => {
    console.error(e);
    await prisma.$disconnect();
    process.exit(1);
  });
