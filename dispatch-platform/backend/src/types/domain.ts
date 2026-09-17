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

/**
 * Capability taxonomy (Patch 1 / Milestone 0C). Runs beside the legacy
 * `Skill` flat-skill enum above, which remains authoritative for dispatch.
 * See docs/CapabilityModel.md.
 */

// Level semantics were frozen in Patch 0C (Domain Contract) and are stored
// as a plain Int on WorkerCapability — these are capability levels, not job
// titles, and are never trade-specific.
export const CapabilityLevel = {
  L1: 1,
  L2: 2,
  L3: 3,
  L4: 4,
} as const;
export type CapabilityLevelT = (typeof CapabilityLevel)[keyof typeof CapabilityLevel];

export const CapabilityLevelDescription: Readonly<Record<number, string>> = {
  1: 'Assist / Directed',
  2: 'Independent, standard work',
  3: 'Independent + basic troubleshooting',
  4: 'Expert / complex & novel',
};

export const CapabilityProvenance = {
  SELF_DECLARED: 'SELF_DECLARED',
  ASSESSED: 'ASSESSED',
  PRACTICALLY_VERIFIED: 'PRACTICALLY_VERIFIED',
  PERFORMANCE_CONFIRMED: 'PERFORMANCE_CONFIRMED',
} as const;
export type CapabilityProvenanceT = (typeof CapabilityProvenance)[keyof typeof CapabilityProvenance];

export const AssessmentType = {
  SELF_DECLARATION: 'SELF_DECLARATION',
  KNOWLEDGE_TEST: 'KNOWLEDGE_TEST',
  PRACTICAL_VERIFICATION: 'PRACTICAL_VERIFICATION',
  PERFORMANCE_REVIEW: 'PERFORMANCE_REVIEW',
} as const;
export type AssessmentTypeT = (typeof AssessmentType)[keyof typeof AssessmentType];
