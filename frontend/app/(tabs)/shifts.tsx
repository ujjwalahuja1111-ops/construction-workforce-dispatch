import { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';

import { api } from '@/src/api/client';
import { Card, Chip, EmptyState } from '@/src/components/ui';
import { colors, spacing, type as t } from '@/src/theme';

function stateTone(s: string): 'success' | 'warning' | 'danger' | 'primary' | 'neutral' | 'info' {
  if (s === 'CLOSED') return 'success';
  if (s === 'CANCELLED') return 'danger';
  if (['WORKING', 'CHECKED_IN', 'RESUMED'].includes(s)) return 'primary';
  if (['BREAK'].includes(s)) return 'warning';
  return 'info';
}

export default function ShiftsHistory() {
  const router = useRouter();
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await api.shifts();
      setItems(r.shifts);
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
        <Text style={styles.title}>Shift history</Text>
        <Text style={styles.subtitle}>Every job you&apos;ve worked on.</Text>
      </View>
      {loading ? (
        <View style={styles.loading}>
          <ActivityIndicator color={colors.primary} />
        </View>
      ) : (
        <ScrollView
          contentContainerStyle={styles.list}
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
          {items.length === 0 ? (
            <EmptyState
              testID="shifts-empty"
              title="No shifts yet"
              hint="Accept an offer from the Jobs tab to start working."
            />
          ) : (
            items.map((s) => {
              const isActive = !['CLOSED', 'CANCELLED'].includes(s.state);
              return (
                <Pressable
                  key={s.id}
                  onPress={() =>
                    router.push({ pathname: '/shift/[id]', params: { id: s.id } })
                  }
                  testID={`shift-item-${s.id}`}
                >
                  <Card style={{ gap: 8 }}>
                    <View style={styles.row}>
                      <View style={{ flex: 1 }}>
                        <Text style={styles.name} numberOfLines={1}>
                          {s.job.project.name}
                        </Text>
                        <Text style={styles.skill}>
                          {s.job.skill.replace('_', ' ')} ·{' '}
                          {new Date(s.shiftDate).toLocaleDateString('en-IN', {
                            day: 'numeric',
                            month: 'short',
                          })}
                        </Text>
                      </View>
                      <Chip label={s.state.replace('_', ' ')} tone={stateTone(s.state)} />
                    </View>
                    <View style={styles.row}>
                      <Text style={styles.meta}>
                        {s.scheduledStart} – {s.scheduledEnd}
                      </Text>
                      <Text style={styles.earned}>
                        ₹{(s.amountEarned || s.wageAmount).toLocaleString('en-IN')}
                      </Text>
                    </View>
                    {isActive ? (
                      <Text style={styles.tap}>Tap to manage →</Text>
                    ) : null}
                  </Card>
                </Pressable>
              );
            })
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
  list: { padding: spacing.md, gap: spacing.md, paddingBottom: spacing.xxl },
  row: { flexDirection: 'row', alignItems: 'center', gap: 8, justifyContent: 'space-between' },
  name: { color: colors.text, ...t.h3 },
  skill: { color: colors.textDim, ...t.small, marginTop: 2 },
  meta: { color: colors.textDim, fontSize: 13 },
  earned: { color: colors.primary, fontSize: 16, fontWeight: '700' },
  tap: { color: colors.primary, fontSize: 12, fontWeight: '600' },
});
