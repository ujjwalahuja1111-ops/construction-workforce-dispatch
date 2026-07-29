import { Request, Response, NextFunction } from 'express';
import { AppError } from '../utils/errors';
import { verifyToken, JwtPayload } from '../utils/jwt';
import { RoleT } from '../types/domain';

export interface AuthedRequest extends Request {
  auth?: JwtPayload;
}

export function requireAuth(req: AuthedRequest, _res: Response, next: NextFunction) {
  const header = req.header('authorization') ?? req.header('Authorization');
  if (!header || !header.toLowerCase().startsWith('bearer ')) {
    throw AppError.unauthorized('Missing bearer token');
  }
  const token = header.slice(7).trim();
  try {
    req.auth = verifyToken(token);
    next();
  } catch {
    throw AppError.unauthorized('Invalid or expired token');
  }
}

export function requireRole(...roles: RoleT[]) {
  return (req: AuthedRequest, _res: Response, next: NextFunction) => {
    if (!req.auth) throw AppError.unauthorized();
    if (!roles.includes(req.auth.role)) throw AppError.forbidden('Role not permitted');
    next();
  };
}
