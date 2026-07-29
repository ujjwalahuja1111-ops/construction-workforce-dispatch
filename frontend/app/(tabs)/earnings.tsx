import { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { api } from '@/src/api/client';
import { Card, EmptyState, SectionHeader, StatTile } from '@/src/components/ui';
import { colors, spacing, type as t } from '@/src/theme';

export default function Earnings() {
  const [data, setData] = useState<{ total: number; week: number; month: number; shifts: any[] } | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await api.earnings();
      setData(r);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <Text style={styles.title}>Earnings</Text>
        <Text style={styles.subtitle}>Track every rupee.</Text>
      </View>
      {loading ? (
        <View style={styles.loading}>
          <ActivityIndicator color={colors.primary} />
        </View>
      ) : (
        <ScrollView
          contentContainerStyle={styles.container}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={async () => {
                setRefreshing(true);
                await load();
                setRefreshing(false);
              }}
              tintColor={colors.primary}
            />
          }
        >
          <Card style={styles.total} testID="earnings-total-card">
            <Text style={styles.totalLabel}>Lifetime earnings</Text>
            <Text style={styles.totalValue}>
              ₹{(data?.total ?? 0).toLocaleString('en-IN')}
            </Text>
          </Card>

          <View style={{ flexDirection: 'row', gap: spacing.md, marginTop: spacing.md }}>
            <StatTile testID="earnings-week" label="Past 7 days" value={`₹${(data?.week ?? 0).toLocaleString('en-IN')}`} />
            <StatTile testID="earnings-month" label="Past 30 days" value={`₹${(data?.month ?? 0).toLocaleString('en-IN')}`} />
          </View>

          <SectionHeader title="Recent payouts" />
          {(data?.shifts ?? []).length === 0 ? (
            <EmptyState
              testID="earnings-empty"
              title="No payouts yet"
              hint="Complete a shift to see your earnings here."
            />
          ) : (
            data!.shifts.map((s) => (
              <Card key={s.id} style={{ marginBottom: spacing.sm }} testID={`earnings-shift-${s.id}`}>
                <View style={styles.row}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.rowTitle}>{s.job?.project?.name || 'Shift'}</Text>
                    <Text style={styles.rowSub}>
                      {new Date(s.shiftDate).toLocaleDateString('en-IN', {
                        day: 'numeric',
                        month: 'short',
                        year: 'numeric',
                      })}
                    </Text>
                  </View>
                  <Text style={styles.amount}>
                    ₹{s.amountEarned.toLocaleString('en-IN')}
                  </Text>
                </View>
              </Card>
            ))
          )}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  header: { paddingHorizontal: spacing.md, paddingTop: spacing.md, paddingBottom: spacing.sm },
  title: { color: colors.text, ...t.h1 },
  subtitle: { color: colors.textDim, ...t.body, marginTop: 4 },
  loading: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  container: { padding: spacing.md, paddingBottom: spacing.xxl },
  total: {
    backgroundColor: colors.primarySoft,
    borderColor: colors.primary,
  },
  totalLabel: { color: colors.primary, fontSize: 12, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.5 },
  totalValue: { color: colors.text, fontSize: 40, fontWeight: '800', marginTop: 6 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  rowTitle: { color: colors.text, ...t.bodyBold },
  rowSub: { color: colors.textDim, fontSize: 12, marginTop: 2 },
  amount: { color: colors.primary, fontSize: 18, fontWeight: '800' },
});
