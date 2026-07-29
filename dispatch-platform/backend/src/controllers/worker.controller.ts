import { Response } from 'express';
import { WorkerService } from '../services/worker.service';
import { AuthedRequest } from '../middleware/auth';
import { z } from '../middleware/validate';
import { Skill } from '../types/domain';

const SkillCodes = Object.values(Skill) as [string, ...string[]];

export const completeProfileSchema = z.object({
  fullName: z.string().min(2),
  skills: z.array(z.enum(SkillCodes)).min(1),
  experienceYears: z.number().int().min(0).max(50),
  dailyWage: z.number().int().min(100).max(10000),
  city: z.string().min(2),
  state: z.string().min(2),
  homeLatitude: z.number().optional(),
  homeLongitude: z.number().optional(),
});

export const locationSchema = z.object({
  latitude: z.number(),
  longitude: z.number(),
});

export const availabilitySchema = z.object({
  available: z.boolean(),
});

export const WorkerController = {
  async me(req: AuthedRequest, res: Response) {
    const data = await WorkerService.me(req.auth!.sub);
    res.json(data);
  },

  async completeProfile(req: AuthedRequest, res: Response) {
    const worker = await WorkerService.completeProfile(req.auth!.sub, req.body);
    res.json({ worker });
  },

  async updateLocation(req: AuthedRequest, res: Response) {
    const { latitude, longitude } = req.body;
    const worker = await WorkerService.updateLocation(req.auth!.sub, latitude, longitude);
    res.json({ worker });
  },

  async setAvailability(req: AuthedRequest, res: Response) {
    const { available } = req.body;
    const worker = await WorkerService.setAvailability(req.auth!.sub, available);
    res.json({ worker });
  },

  async offers(req: AuthedRequest, res: Response) {
    const offers = await WorkerService.listPendingOffers(req.auth!.sub);
    res.json({ offers });
  },

  async shifts(req: AuthedRequest, res: Response) {
    const shifts = await WorkerService.listShiftHistory(req.auth!.sub);
    res.json({ shifts });
  },

  async earnings(req: AuthedRequest, res: Response) {
    const earnings = await WorkerService.earnings(req.auth!.sub);
    res.json(earnings);
  },
};
