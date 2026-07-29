import { Router } from 'express';
import { ShiftController, geoSchema } from '../controllers/shift.controller';
import { requireAuth, requireRole } from '../middleware/auth';
import { validateBody } from '../middleware/validate';
import { Role } from '../types/domain';

const r = Router();
r.use(requireAuth, requireRole(Role.WORKER));

r.get('/active', ShiftController.active);
r.get('/:id', ShiftController.get);
r.post('/:id/travel', ShiftController.travel);
r.post('/:id/arrive', ShiftController.arrive);
r.post('/:id/check-in', validateBody(geoSchema), ShiftController.checkIn);
r.post('/:id/start-work', ShiftController.startWork);
r.post('/:id/break', ShiftController.startBreak);
r.post('/:id/resume', ShiftController.resume);
r.post('/:id/complete', ShiftController.complete);
r.post('/:id/check-out', validateBody(geoSchema), ShiftController.checkOut);
r.post('/:id/close', ShiftController.close);

export default r;
