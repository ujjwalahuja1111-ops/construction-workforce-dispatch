import { Router } from 'express';
import authRoutes from './auth.routes';
import workerRoutes from './worker.routes';
import jobRoutes from './job.routes';
import shiftRoutes from './shift.routes';
import notificationRoutes from './notification.routes';

const api = Router();

api.get('/health', (_req, res) =>
  res.json({ status: 'ok', service: 'dispatch-backend', ts: new Date().toISOString() }),
);

api.use('/auth', authRoutes);
api.use('/worker', workerRoutes);
api.use('/jobs', jobRoutes);
api.use('/shifts', shiftRoutes);
api.use('/notifications', notificationRoutes);

export default api;
