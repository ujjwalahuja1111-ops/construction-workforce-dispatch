import { Request, Response } from 'express';
import { AuthService } from '../services/auth.service';
import { z } from '../middleware/validate';

export const requestOtpSchema = z.object({
  phone: z.string().min(10),
  role: z.enum(['WORKER', 'CONTRACTOR', 'ADMIN']).optional(),
});

export const verifyOtpSchema = z.object({
  phone: z.string().min(10),
  code: z.string().min(4).max(8),
});

export const AuthController = {
  async requestOtp(req: Request, res: Response) {
    const { phone, role } = req.body as z.infer<typeof requestOtpSchema>;
    const result = await AuthService.requestOtp(phone, role);
    res.json(result);
  },

  async verifyOtp(req: Request, res: Response) {
    const { phone, code } = req.body as z.infer<typeof verifyOtpSchema>;
    const result = await AuthService.verifyOtp(phone, code);
    res.json(result);
  },
};
