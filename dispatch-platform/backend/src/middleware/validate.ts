import { z, ZodSchema } from 'zod';
import { Request, Response, NextFunction } from 'express';

/**
 * Runs a Zod schema against `req.body` and replaces it with the parsed value.
 * Any ZodError bubbles up to the global error handler.
 */
export function validateBody<T extends ZodSchema>(schema: T) {
  return (req: Request, _res: Response, next: NextFunction) => {
    req.body = schema.parse(req.body);
    next();
  };
}

export function validateQuery<T extends ZodSchema>(schema: T) {
  return (req: Request, _res: Response, next: NextFunction) => {
    // express typing keeps req.query as ParsedQs; overwrite is safe here
    (req as unknown as { query: unknown }).query = schema.parse(req.query);
    next();
  };
}

export { z };
