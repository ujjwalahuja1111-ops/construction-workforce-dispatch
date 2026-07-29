import { Router } from 'express';
import { AuthController, requestOtpSchema, verifyOtpSchema } from '../controllers/auth.controller';
import { validateBody } from '../middleware/validate';

const r = Router();
r.post('/otp/request', validateBody(requestOtpSchema), AuthController.requestOtp);
r.post('/otp/verify', validateBody(verifyOtpSchema), AuthController.verifyOtp);
export default r;
