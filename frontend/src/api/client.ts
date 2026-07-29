import { storage } from '../utils/storage';

const BASE_URL = process.env.EXPO_PUBLIC_BACKEND_URL as string;
const TOKEN_KEY = 'dispatch.auth.token';

export interface ApiError {
  code: string;
  message: string;
  details?: unknown;
}

export class ApiException extends Error {
  status: number;
  code: string;
  details?: unknown;
  constructor(status: number, err: ApiError) {
    super(err.message);
    this.status = status;
    this.code = err.code;
    this.details = err.details;
  }
}

async function authHeader(): Promise<Record<string, string>> {
  const t = await storage.secureGet(TOKEN_KEY, '');
  return t ? { authorization: `Bearer ${t}` } : {};
}

async function request<T = unknown>(
  method: string,
  path: string,
  body?: unknown,
  opts: { anonymous?: boolean } = {},
): Promise<T> {
  const headers: Record<string, string> = {
    'content-type': 'application/json',
  };
  if (!opts.anonymous) Object.assign(headers, await authHeader());

  const res = await fetch(`${BASE_URL}/api${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });

  const text = await res.text();
  const json = text ? JSON.parse(text) : {};

  if (!res.ok) {
    const err: ApiError = (json && json.error) || {
      code: 'HTTP_ERROR',
      message: `HTTP ${res.status}`,
    };
    throw new ApiException(res.status, err);
  }
  return json as T;
}

export const api = {
  // ─── Auth ──────────────────────────────────────────────────────────
  requestOtp: (phone: string) =>
    request<{ userId: string; phone: string; isNewUser: boolean; devOtp?: string }>(
      'POST',
      '/auth/otp/request',
      { phone },
      { anonymous: true },
    ),

  verifyOtp: (phone: string, code: string) =>
    request<{ token: string; user: any; profileComplete: boolean }>(
      'POST',
      '/auth/otp/verify',
      { phone, code },
      { anonymous: true },
    ),

  // ─── Worker ─────────────────────────────────────────────────────────
  me: () => request<{ user: any; worker: any }>('GET', '/worker/me'),

  completeProfile: (data: {
    fullName: string;
    skills: string[];
    experienceYears: number;
    dailyWage: number;
    city: string;
    state: string;
    homeLatitude?: number;
    homeLongitude?: number;
  }) => request<{ worker: any }>('POST', '/worker/profile', data),

  updateLocation: (latitude: number, longitude: number) =>
    request<{ worker: any }>('POST', '/worker/location', { latitude, longitude }),

  setAvailability: (available: boolean) =>
    request<{ worker: any }>('POST', '/worker/availability', { available }),

  offers: () => request<{ offers: any[] }>('GET', '/worker/offers'),

  shifts: () => request<{ shifts: any[] }>('GET', '/worker/shifts'),

  earnings: () =>
    request<{ total: number; week: number; month: number; shifts: any[] }>(
      'GET',
      '/worker/earnings',
    ),

  // ─── Jobs ───────────────────────────────────────────────────────────
  acceptOffer: (offerId: string) =>
    request<{ shift: any; offer: any }>('POST', '/jobs/offers/accept', { offerId }),
  declineOffer: (offerId: string) =>
    request<{ offer: any }>('POST', '/jobs/offers/decline', { offerId }),

  // ─── Shifts ─────────────────────────────────────────────────────────
  activeShift: () => request<{ shift: any | null }>('GET', '/shifts/active'),
  getShift: (id: string) => request<{ shift: any }>('GET', `/shifts/${id}`),
  shiftAction: (
    id: string,
    action:
      | 'travel'
      | 'arrive'
      | 'check-in'
      | 'start-work'
      | 'break'
      | 'resume'
      | 'complete'
      | 'check-out'
      | 'close',
    body?: unknown,
  ) => request<{ shift: any }>('POST', `/shifts/${id}/${action}`, body ?? {}),

  // ─── Notifications ──────────────────────────────────────────────────
  notifications: () =>
    request<{ notifications: any[] }>('GET', '/notifications'),
  markAllRead: () => request('POST', '/notifications/read-all'),
};

export const TOKEN_STORAGE_KEY = TOKEN_KEY;
