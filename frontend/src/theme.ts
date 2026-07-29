/**
 * Design tokens for the Worker mobile app.
 *
 * Palette rationale: construction sites are outdoors with harsh light.
 * We use a very dark charcoal background with high-contrast text and a
 * safety-orange primary — easily glanceable in bright sunlight, low
 * cognitive load, and instantly recognisable as an action.
 */

export const colors = {
  // surfaces
  bg:            '#0A0A0B',   // near-black canvas
  surface:       '#161618',   // card default
  surfaceAlt:    '#1F1F22',   // pressed / secondary card
  border:        '#2A2A2E',
  divider:       '#232326',

  // text
  text:          '#F5F5F7',
  textDim:       '#A0A0A6',
  textMuted:     '#6E6E73',
  textInverse:   '#0A0A0B',

  // brand
  primary:       '#FF6B00',   // safety orange
  primaryDim:    '#B34B00',
  primarySoft:   '#291204',

  // semantic
  success:       '#22C55E',
  successSoft:   '#0E2A18',
  warning:       '#F59E0B',
  warningSoft:   '#2A1F08',
  danger:        '#EF4444',
  dangerSoft:    '#2A0F0F',
  info:          '#3B82F6',
  infoSoft:      '#0F1B2A',
};

export const spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  xxl: 48,
};

export const radius = {
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  pill: 999,
};

export const type = {
  displayXl: { fontSize: 40, fontWeight: '800' as const, letterSpacing: -0.5 },
  displayLg: { fontSize: 32, fontWeight: '700' as const, letterSpacing: -0.3 },
  h1:        { fontSize: 26, fontWeight: '700' as const },
  h2:        { fontSize: 20, fontWeight: '700' as const },
  h3:        { fontSize: 18, fontWeight: '600' as const },
  body:      { fontSize: 15, fontWeight: '400' as const },
  bodyBold:  { fontSize: 15, fontWeight: '600' as const },
  small:     { fontSize: 13, fontWeight: '400' as const },
  smallBold: { fontSize: 13, fontWeight: '600' as const },
  tiny:      { fontSize: 11, fontWeight: '600' as const, letterSpacing: 0.5 },
};

// Touch targets: min 48pt (Android material) since users often wear gloves.
export const touch = {
  minHeight: 52,
  minWidth: 52,
};
