/**
 * Domain-scoped enums / constants shared across services and controllers.
 * Kept as `const` objects (not TS enums) so they survive Prisma's `String`
 * columns without runtime coupling.
 */

export const Role = {
  WORKER: 'WORKER',
  CONTRACTOR: 'CONTRACTOR',
  ADMIN: 'ADMIN',
} as const;
export type RoleT = (typeof Role)[keyof typeof Role];

export const Skill = {
  MASON: 'MASON',
  HELPER: 'HELPER',
  BAR_BENDER: 'BAR_BENDER',
  CARPENTER: 'CARPENTER',
  PAINTER: 'PAINTER',
  ELECTRICIAN: 'ELECTRICIAN',
  PLUMBER: 'PLUMBER',
  WELDER: 'WELDER',
  TILE_LAYER: 'TILE_LAYER',
  SUPERVISOR: 'SUPERVISOR',
} as const;
export type SkillT = (typeof Skill)[keyof typeof Skill];

export const ShiftState = {
  CREATED: 'CREATED',
  OFFERED: 'OFFERED',
  ACCEPTED: 'ACCEPTED',
  TRAVELLING: 'TRAVELLING',
  ARRIVED: 'ARRIVED',
  CHECKED_IN: 'CHECKED_IN',
  WORKING: 'WORKING',
  BREAK: 'BREAK',
  RESUMED: 'RESUMED',
  COMPLETED: 'COMPLETED',
  CHECKED_OUT: 'CHECKED_OUT',
  CLOSED: 'CLOSED',
  CANCELLED: 'CANCELLED',
} as const;
export type ShiftStateT = (typeof ShiftState)[keyof typeof ShiftState];

export const JobStatus = {
  OPEN: 'OPEN',
  DISPATCHING: 'DISPATCHING',
  FULFILLED: 'FULFILLED',
  CANCELLED: 'CANCELLED',
  CLOSED: 'CLOSED',
} as const;

export const OfferStatus = {
  PENDING: 'PENDING',
  ACCEPTED: 'ACCEPTED',
  DECLINED: 'DECLINED',
  EXPIRED: 'EXPIRED',
} as const;

export const NotificationType = {
  JOB_OFFER: 'JOB_OFFER',
  SHIFT_UPDATE: 'SHIFT_UPDATE',
  RATING: 'RATING',
  SYSTEM: 'SYSTEM',
} as const;
