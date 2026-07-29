import jwt, { SignOptions } from 'jsonwebtoken';
import { env } from '../config/env';
import { RoleT } from '../types/domain';

export interface JwtPayload {
  sub: string;    // user id
  role: RoleT;
  phone: string;
}

export function signToken(payload: JwtPayload): string {
  return jwt.sign(payload, env.jwtSecret, {
    expiresIn: env.jwtExpiresIn,
  } as SignOptions);
}

export function verifyToken(token: string): JwtPayload {
  return jwt.verify(token, env.jwtSecret) as JwtPayload;
}
