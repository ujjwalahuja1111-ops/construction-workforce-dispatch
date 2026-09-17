// Minimal ESLint flat config for the backend.
// Scope: establish a real, working lint gate (Milestone 0A) without a
// large stylistic rewrite. Uses typescript-eslint's non-type-checked
// "recommended" ruleset — fast, no tsconfig project service required,
// and matches the checks the codebase already passes under `tsc --noEmit`.
const tseslint = require('typescript-eslint');

module.exports = tseslint.config(
  {
    ignores: ['dist/**', 'node_modules/**', 'prisma/**'],
  },
  ...tseslint.configs.recommended,
  {
    rules: {
      // Console logging is used deliberately throughout this backend
      // (dev OTP echo, request logging, error logging) — not a lint concern.
      'no-console': 'off',
      // The codebase already uses a leading underscore as its convention for
      // intentionally-unused parameters (Express error handlers require the
      // full (err, req, res, next) signature; some callbacks ignore an arg).
      // Recognize that convention instead of flagging it.
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
    },
  },
);
