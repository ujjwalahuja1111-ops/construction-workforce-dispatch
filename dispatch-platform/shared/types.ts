/**
 * Cross-project shared TypeScript types. Backend and web frontends can import
 * from `../shared/types` (or wire a workspace path alias) to keep API contracts
 * in one place.
 *
 * Kept intentionally minimal: only the shapes actually returned by the API.
 */

export type Role = 'WORKER' | 'CONTRACTOR' | 'ADMIN';

export type Skill =
  | 'MASON'
  | 'HELPER'
  | 'BAR_BENDER'
  | 'CARPENTER'
  | 'PAINTER'
  | 'ELECTRICIAN'
  | 'PLUMBER'
  | 'WELDER'
  | 'TILE_LAYER'
  | 'SUPERVISOR';

export type ShiftState =
  | 'CREATED' | 'OFFERED' | 'ACCEPTED' | 'TRAVELLING' | 'ARRIVED'
  | 'CHECKED_IN' | 'WORKING' | 'BREAK' | 'RESUMED' | 'COMPLETED'
  | 'CHECKED_OUT' | 'CLOSED' | 'CANCELLED';

export type JobStatus =
  | 'OPEN' | 'DISPATCHING' | 'FULFILLED' | 'CANCELLED' | 'CLOSED';

export type OfferStatus = 'PENDING' | 'ACCEPTED' | 'DECLINED' | 'EXPIRED';

export interface ApiErrorPayload {
  code: string;
  message: string;
  details?: unknown;
}

export interface AuthUser {
  id: string;
  phone: string;
  fullName: string;
  role: Role;
  isVerified: boolean;
}

export interface AuthResponse {
  token: string;
  user: AuthUser;
  profileComplete: boolean;
}
