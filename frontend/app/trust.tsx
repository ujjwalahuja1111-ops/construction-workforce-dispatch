import { ScrollView, StyleSheet, Text, View, Pressable } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';

import { useAuth } from '@/src/context/AuthContext';
import { Card, Chip } from '@/src/components/ui';
import { colors, radius, spacing, type as t } from '@/src/theme';

export default function Trust() {
  const router = useRouter();
  const { worker } = useAuth();
  const score = worker?.trustScore ?? 0;
  const tone: 'success' | 'warning' | 'danger' =
    score >= 80 ? 'success' : score >= 60 ? 'warning' : 'danger';

  const rows: { label: string; value: string; hint: string; icon: any }[] = [
    {
      icon: 'checkmark-circle',
      label: 'Attendance',
      value: `${worker?.completedShifts ?? 0}/${worker?.totalShifts ?? 0}`,
      hint: 'shifts completed on time',
    },
    {
      icon: 'thumbs-up',
      label: 'Acceptance',
      value:
        (worker?.acceptedOffers ?? 0) + (worker?.declinedOffers ?? 0) === 0
          ? '—'
          : `${Math.round(
              ((worker?.acceptedOffers ?? 0) /
                ((worker?.acceptedOffers ?? 0) + (worker?.declinedOffers ?? 0))) *
                100,
            )}%`,
      hint: 'offers you accepted',
    },
    {
      icon: 'close-circle',
      label: 'Cancellations',
      value: String(worker?.cancelledShifts ?? 0),
      hint: 'lower is better',
    },
    {
      icon: 'star',
      label: 'Avg rating',
      value: (worker?.avgRating ?? 0).toFixed(1),
      hint: 'out of 5',
    },
  ];

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} style={styles.back} hitSlop={12} testID="trust-back">
          <Ionicons name="chevron-back" size={26} color={colors.text} />
        </Pressable>
        <Text style={styles.title}>Trust score</Text>
        <View style={{ width: 34 }} />
      </View>

      <ScrollView contentContainerStyle={styles.container}>
        <Card style={styles.hero} testID="trust-hero">
          <View style={styles.ringWrap}>
            <View style={[styles.ring, { borderColor: colors.primary }]}>
              <Text style={styles.ringScore}>{score}</Text>
              <Text style={styles.ringOf}>/100</Text>
            </View>
          </View>
          <Chip label={score >= 80 ? 'Excellent' : score >= 60 ? 'Good' : 'Low'} tone={tone} />
          <Text style={styles.heroHint}>
            Higher trust means you&apos;re dispatched first when new work comes in.
          </Text>
        </Card>

        <Text style={styles.section}>What builds your score</Text>
        {rows.map((r) => (
          <Card key={r.label} style={styles.row} testID={`trust-row-${r.label.toLowerCase()}`}>
            <Ionicons name={r.icon} size={20} color={colors.primary} />
            <View style={{ flex: 1 }}>
              <Text style={styles.rowLabel}>{r.label}</Text>
              <Text style={styles.rowHint}>{r.hint}</Text>
            </View>
            <Text style={styles.rowValue}>{r.value}</Text>
          </Card>
        ))}

        <View style={{ height: 24 }} />
        <Text style={styles.help}>
          Your score is recalculated automatically each time you complete a shift or respond to an offer.
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    justifyContent: 'space-between',
  },
  back: { padding: 4 },
  title: { color: colors.text, ...t.h2 },
  container: { padding: spacing.md, paddingBottom: spacing.xxl },
  hero: { alignItems: 'center', paddingVertical: spacing.xl },
  ringWrap: { marginBottom: spacing.md },
  ring: {
    width: 160,
    height: 160,
    borderRadius: 80,
    borderWidth: 8,
    alignItems: 'center',
    justifyContent: 'center',
  },
  ringScore: { color: colors.text, fontSize: 56, fontWeight: '800' },
  ringOf: { color: colors.textDim, fontSize: 14, marginTop: -6 },
  heroHint: { color: colors.textDim, textAlign: 'center', marginTop: spacing.md, ...t.small },
  section: { color: colors.text, ...t.h3, marginTop: spacing.xl, marginBottom: spacing.sm },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    marginBottom: spacing.sm,
  },
  rowLabel: { color: colors.text, ...t.bodyBold },
  rowHint: { color: colors.textDim, fontSize: 12, marginTop: 2 },
  rowValue: { color: colors.primary, fontSize: 20, fontWeight: '800' },
  help: { color: colors.textMuted, ...t.small, textAlign: 'center' },
});
