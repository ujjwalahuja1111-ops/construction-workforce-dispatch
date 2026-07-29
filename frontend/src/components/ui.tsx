import { StyleSheet, Text, View, ViewStyle, StyleProp, TextStyle } from 'react-native';
import { colors, radius, spacing, type as t } from '../theme';

export function Card({
  children,
  style,
  testID,
}: {
  children: React.ReactNode;
  style?: StyleProp<ViewStyle>;
  testID?: string;
}) {
  return (
    <View testID={testID} style={[styles.card, style]}>
      {children}
    </View>
  );
}

export function Chip({
  label,
  tone = 'neutral',
  testID,
}: {
  label: string;
  tone?: 'neutral' | 'success' | 'warning' | 'danger' | 'primary' | 'info';
  testID?: string;
}) {
  const map: Record<string, [string, string]> = {
    neutral: [colors.surfaceAlt, colors.textDim],
    success: [colors.successSoft, colors.success],
    warning: [colors.warningSoft, colors.warning],
    danger:  [colors.dangerSoft, colors.danger],
    primary: [colors.primarySoft, colors.primary],
    info:    [colors.infoSoft, colors.info],
  };
  const [bg, fg] = map[tone];
  return (
    <View testID={testID} style={[styles.chip, { backgroundColor: bg }]}>
      <Text style={[t.tiny, { color: fg, textTransform: 'uppercase' }]}>{label}</Text>
    </View>
  );
}

export function StatTile({
  label,
  value,
  hint,
  style,
  testID,
}: {
  label: string;
  value: string;
  hint?: string;
  style?: StyleProp<ViewStyle>;
  testID?: string;
}) {
  return (
    <View testID={testID} style={[styles.stat, style]}>
      <Text style={styles.statLabel}>{label}</Text>
      <Text style={styles.statValue}>{value}</Text>
      {hint ? <Text style={styles.statHint}>{hint}</Text> : null}
    </View>
  );
}

export function SectionHeader({ title, right, style }: { title: string; right?: React.ReactNode; style?: StyleProp<ViewStyle> }) {
  return (
    <View style={[styles.sectionHeader, style]}>
      <Text style={styles.sectionTitle}>{title}</Text>
      {right}
    </View>
  );
}

export function EmptyState({ title, hint, testID }: { title: string; hint?: string; testID?: string }) {
  return (
    <View testID={testID} style={styles.empty}>
      <Text style={[t.h3, { color: colors.textDim, textAlign: 'center' }]}>{title}</Text>
      {hint ? <Text style={[t.small, { color: colors.textMuted, marginTop: 8, textAlign: 'center' }]}>{hint}</Text> : null}
    </View>
  );
}

export function Label({ children, style }: { children: React.ReactNode; style?: StyleProp<TextStyle> }) {
  return <Text style={[styles.label, style]}>{children}</Text>;
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  chip: {
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: radius.pill,
    alignSelf: 'flex-start',
  },
  stat: {
    flex: 1,
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  statLabel: {
    color: colors.textDim,
    fontSize: 12,
    fontWeight: '600',
    textTransform: 'uppercase',
    letterSpacing: 0.4,
  },
  statValue: {
    color: colors.text,
    fontSize: 24,
    fontWeight: '800',
    marginTop: 6,
  },
  statHint: {
    color: colors.textMuted,
    fontSize: 12,
    marginTop: 2,
  },
  sectionHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.sm,
    marginTop: spacing.lg,
  },
  sectionTitle: {
    color: colors.text,
    fontSize: 18,
    fontWeight: '700',
  },
  empty: {
    padding: spacing.xl,
    alignItems: 'center',
    justifyContent: 'center',
  },
  label: {
    color: colors.textDim,
    fontSize: 12,
    fontWeight: '600',
    textTransform: 'uppercase',
    letterSpacing: 0.4,
    marginBottom: 6,
  },
});
