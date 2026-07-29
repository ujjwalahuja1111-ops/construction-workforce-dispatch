import dotenv from 'dotenv';
import path from 'path';

// Load .env from the backend root
dotenv.config({ path: path.resolve(__dirname, '../../.env') });

function required(key: string, fallback?: string): string {
  const v = process.env[key] ?? fallback;
  if (v === undefined) {
    throw new Error(`Missing required env: ${key}`);
  }
  return v;
}

export const env = {
  nodeEnv: process.env.NODE_ENV ?? 'development',
  port: parseInt(required('PORT', '8002'), 10),
  apiPrefix: process.env.API_PREFIX ?? '/api',

  databaseUrl: required('DATABASE_URL'),
  jwtSecret: required('JWT_SECRET'),
  jwtExpiresIn: process.env.JWT_EXPIRES_IN ?? '30d',

  devOtpCode: process.env.DEV_OTP_CODE ?? '123456',
  otpTtlSeconds: parseInt(process.env.OTP_TTL_SECONDS ?? '300', 10),

  corsOrigin: process.env.CORS_ORIGIN ?? '*',

  dispatchMaxRadiusKm: parseFloat(process.env.DISPATCH_MAX_RADIUS_KM ?? '25'),
  dispatchMaxCandidates: parseInt(process.env.DISPATCH_MAX_CANDIDATES ?? '15', 10),
};
