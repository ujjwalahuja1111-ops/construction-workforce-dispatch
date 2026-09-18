import { Router } from 'express';
import { WorkerController, completeProfileSchema, locationSchema, availabilitySchema } from '../controllers/worker.controller';
import { WorkerCapabilityController, selfDeclareCapabilitySchema } from '../controllers/worker-capability.controller';
import { requireAuth, requireRole } from '../middleware/auth';
import { validateBody } from '../middleware/validate';
import { Role } from '../types/domain';

const r = Router();
r.use(requireAuth, requireRole(Role.WORKER));

r.get('/me', WorkerController.me);
r.post('/profile', validateBody(completeProfileSchema), WorkerController.completeProfile);
r.post('/location', validateBody(locationSchema), WorkerController.updateLocation);
r.post('/availability', validateBody(availabilitySchema), WorkerController.setAvailability);
r.get('/offers', WorkerController.offers);
r.get('/shifts', WorkerController.shifts);
r.get('/earnings', WorkerController.earnings);

// Patch 2 — Worker Capability API (Self-Declaration). Same
// requireAuth/requireRole(WORKER) boundary as every other route above; no
// new middleware.
r.post('/capabilities', validateBody(selfDeclareCapabilitySchema), WorkerCapabilityController.selfDeclare);
r.get('/capabilities', WorkerCapabilityController.list);

export default r;
