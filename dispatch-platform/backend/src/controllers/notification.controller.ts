import { Response } from 'express';
import { NotificationService } from '../services/notification.service';
import { AuthedRequest } from '../middleware/auth';

export const NotificationController = {
  async list(req: AuthedRequest, res: Response) {
    const unreadOnly = req.query.unread === 'true';
    const items = await NotificationService.listForUser(req.auth!.sub, unreadOnly);
    res.json({ notifications: items });
  },
  async markRead(req: AuthedRequest, res: Response) {
    const n = await NotificationService.markRead(req.auth!.sub, req.params.id);
    res.json({ notification: n });
  },
  async markAllRead(req: AuthedRequest, res: Response) {
    const r = await NotificationService.markAllRead(req.auth!.sub);
    res.json(r);
  },
};
