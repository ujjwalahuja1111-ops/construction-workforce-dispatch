import { Router } from 'express';
import { JobController, offerActionSchema } from '../controllers/job.controller';
import { requireAuth, requireRole } from '../middleware/auth';
import { validateBody } from '../middleware/validate';
import { Role } from '../types/domain';

const r = Router();
r.use(requireAuth, requireRole(Role.WORKER));

r.post('/offers/accept', validateBody(offerActionSchema), JobController.acceptOffer);
r.post('/offers/decline', validateBody(offerActionSchema), JobController.declineOffer);

export default r;
