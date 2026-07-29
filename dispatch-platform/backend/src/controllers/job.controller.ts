import { Response } from 'express';
import { JobService } from '../services/job.service';
import { AuthedRequest } from '../middleware/auth';
import { z } from '../middleware/validate';

export const offerActionSchema = z.object({
  offerId: z.string().uuid(),
});

export const JobController = {
  async acceptOffer(req: AuthedRequest, res: Response) {
    const { offerId } = req.body;
    const result = await JobService.acceptOffer(req.auth!.sub, offerId);
    res.json(result);
  },

  async declineOffer(req: AuthedRequest, res: Response) {
    const { offerId } = req.body;
    const result = await JobService.declineOffer(req.auth!.sub, offerId);
    res.json({ offer: result });
  },
};
