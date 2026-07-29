import { Response } from 'express';
import { ShiftService } from '../services/shift.service';
import { AuthedRequest } from '../middleware/auth';
import { z } from '../middleware/validate';

export const geoSchema = z.object({
  latitude: z.number(),
  longitude: z.number(),
});

export const ShiftController = {
  async active(req: AuthedRequest, res: Response) {
    const shift = await ShiftService.currentActive(req.auth!.sub);
    res.json({ shift });
  },

  async get(req: AuthedRequest, res: Response) {
    const shift = await ShiftService.get(req.params.id, req.auth!.sub);
    res.json({ shift });
  },

  async travel(req: AuthedRequest, res: Response) {
    const b = req.body as Partial<z.infer<typeof geoSchema>>;
    const s = await ShiftService.travel(req.params.id, req.auth!.sub, b.latitude, b.longitude);
    res.json({ shift: s });
  },
  async arrive(req: AuthedRequest, res: Response) {
    const b = req.body as Partial<z.infer<typeof geoSchema>>;
    const s = await ShiftService.arrive(req.params.id, req.auth!.sub, b.latitude, b.longitude);
    res.json({ shift: s });
  },
  async checkIn(req: AuthedRequest, res: Response) {
    const { latitude, longitude } = req.body;
    const s = await ShiftService.checkIn(req.params.id, req.auth!.sub, latitude, longitude);
    res.json({ shift: s });
  },
  async startWork(req: AuthedRequest, res: Response) {
    const s = await ShiftService.startWork(req.params.id, req.auth!.sub);
    res.json({ shift: s });
  },
  async startBreak(req: AuthedRequest, res: Response) {
    const s = await ShiftService.startBreak(req.params.id, req.auth!.sub);
    res.json({ shift: s });
  },
  async resume(req: AuthedRequest, res: Response) {
    const s = await ShiftService.resume(req.params.id, req.auth!.sub);
    res.json({ shift: s });
  },
  async complete(req: AuthedRequest, res: Response) {
    const s = await ShiftService.complete(req.params.id, req.auth!.sub);
    res.json({ shift: s });
  },
  async checkOut(req: AuthedRequest, res: Response) {
    const { latitude, longitude } = req.body;
    const s = await ShiftService.checkOut(req.params.id, req.auth!.sub, latitude, longitude);
    res.json({ shift: s });
  },
  async close(req: AuthedRequest, res: Response) {
    const s = await ShiftService.close(req.params.id, req.auth!.sub);
    res.json({ shift: s });
  },
};
