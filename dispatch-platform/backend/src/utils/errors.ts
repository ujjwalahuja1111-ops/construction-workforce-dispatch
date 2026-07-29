/**
 * Uniform HTTP error class. All controllers/services throw AppError; the
 * global error middleware translates it to a JSON response.
 */
export class AppError extends Error {
  public statusCode: number;
  public code: string;
  public details?: unknown;

  constructor(statusCode: number, code: string, message: string, details?: unknown) {
    super(message);
    this.statusCode = statusCode;
    this.code = code;
    this.details = details;
  }

  static badRequest(msg: string, details?: unknown) {
    return new AppError(400, 'BAD_REQUEST', msg, details);
  }
  static unauthorized(msg = 'Unauthorized') {
    return new AppError(401, 'UNAUTHORIZED', msg);
  }
  static forbidden(msg = 'Forbidden') {
    return new AppError(403, 'FORBIDDEN', msg);
  }
  static notFound(msg = 'Not Found') {
    return new AppError(404, 'NOT_FOUND', msg);
  }
  static conflict(msg: string) {
    return new AppError(409, 'CONFLICT', msg);
  }
  static invalidState(msg: string) {
    return new AppError(422, 'INVALID_STATE', msg);
  }
}
