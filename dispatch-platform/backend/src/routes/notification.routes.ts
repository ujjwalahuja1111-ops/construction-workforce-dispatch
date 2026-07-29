import { Router } from 'express';
import { NotificationController } from '../controllers/notification.controller';
import { requireAuth } from '../middleware/auth';

const r = Router();
r.use(requireAuth);
r.get('/', NotificationController.list);
r.post('/:id/read', NotificationController.markRead);
r.post('/read-all', NotificationController.markAllRead);
export default r;
