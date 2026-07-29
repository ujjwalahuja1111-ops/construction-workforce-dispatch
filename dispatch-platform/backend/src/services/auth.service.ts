import { prisma } from '../config/prisma';
import { env } from '../config/env';
import { AppError } from '../utils/errors';
import { signToken } from '../utils/jwt';
import { RoleT, Role } from '../types/domain';

/**
 * AuthService - phone + OTP + JWT.
 *
 * Dev mode:
 *   - OTP is a fixed constant (env.devOtpCode, default "123456")
 *   - `requestOtp` returns the code in the response for developer convenience
 *     and also logs it to the server console.
 *
 * Prod mode:
 *   - Wire a real SMS provider in `sendOtpViaSms()` and drop `otp` from the
 *     response payload.
 */
export class AuthService {
  static normalizePhone(input: string): string {
    const digits = input.replace(/\D/g, '');
    // Accept +91XXXXXXXXXX, 91XXXXXXXXXX, or 10-digit local
    const last10 = digits.slice(-10);
    if (last10.length !== 10) {
      throw AppError.badRequest('Phone must contain 10 digits');
    }
    return `+91${last10}`;
  }

  static async requestOtp(rawPhone: string, role?: RoleT) {
    const phone = this.normalizePhone(rawPhone);

    // Only WORKER can auto-register via mobile. CONTRACTOR/ADMIN must be
    // provisioned by an admin. We still allow OTP requests for existing
    // contractors/admins, but never auto-create them.
    let user = await prisma.user.findUnique({ where: { phone } });

    if (!user && role && role !== Role.WORKER) {
      throw AppError.forbidden(
        'Only worker accounts can self-register. Contact admin.',
      );
    }

    if (!user) {
      user = await prisma.user.create({
        data: {
          phone,
          role: Role.WORKER,
          fullName: 'New Worker',
          isVerified: false,
        },
      });
    }

    const code = env.devOtpCode;
    const expiresAt = new Date(Date.now() + env.otpTtlSeconds * 1000);
    await prisma.otp.create({
      data: { userId: user.id, code, expiresAt },
    });

    // eslint-disable-next-line no-console
    console.log(`[OTP] phone=${phone} code=${code} (dev-mode)`);

    return {
      userId: user.id,
      phone,
      isNewUser: !user.isVerified,
      // dev-only echo of OTP; remove in production
      devOtp: env.nodeEnv === 'production' ? undefined : code,
    };
  }

  static async verifyOtp(rawPhone: string, code: string) {
    const phone = this.normalizePhone(rawPhone);
    const user = await prisma.user.findUnique({ where: { phone } });
    if (!user) throw AppError.notFound('No account for this phone');

    const otp = await prisma.otp.findFirst({
      where: {
        userId: user.id,
        code,
        consumed: false,
        expiresAt: { gt: new Date() },
      },
      orderBy: { createdAt: 'desc' },
    });
    if (!otp) throw AppError.unauthorized('Invalid or expired OTP');

    await prisma.$transaction([
      prisma.otp.update({ where: { id: otp.id }, data: { consumed: true } }),
      prisma.user.update({
        where: { id: user.id },
        data: { isVerified: true },
      }),
    ]);

    // If worker and no profile exists yet, they'll need to complete registration
    const worker =
      user.role === Role.WORKER
        ? await prisma.worker.findUnique({ where: { userId: user.id } })
        : null;
    const contractor =
      user.role === Role.CONTRACTOR
        ? await prisma.contractor.findUnique({ where: { userId: user.id } })
        : null;

    const token = signToken({
      sub: user.id,
      role: user.role as RoleT,
      phone: user.phone,
    });

    return {
      token,
      user: {
        id: user.id,
        phone: user.phone,
        fullName: user.fullName,
        role: user.role,
        isVerified: true,
      },
      profileComplete: user.role === Role.WORKER ? !!worker : !!contractor || user.role === Role.ADMIN,
    };
  }
}
