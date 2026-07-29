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
import { Ionicons } from '@expo/vector-icons';

import { api, ApiException } from '@/src/api/client';
import { Card, Chip, EmptyState } from '@/src/components/ui';
import { Button } from '@/src/components/Button';
import { colors, radius, spacing, type as t } from '@/src/theme';

export default function Jobs() {
  const router = useRouter();
  const [offers, setOffers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await api.offers();
      setOffers(r.offers);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function onRefresh() {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  }

  async function accept(offer: any) {
    setBusyId(offer.id);
    setMessage(null);
    try {
      const r = await api.acceptOffer(offer.id);
      setMessage('Accepted — check your active shift.');
      await load();
      router.push({ pathname: '/shift/[id]', params: { id: r.shift.id } });
    } catch (e) {
      setMessage(e instanceof ApiException ? e.message : 'Could not accept');
    } finally {
      setBusyId(null);
    }
  }

  async function decline(offer: any) {
    setBusyId(offer.id);
    setMessage(null);
    try {
      await api.declineOffer(offer.id);
      await load();
    } catch (e) {
      setMessage(e instanceof ApiException ? e.message : 'Could not decline');
    } finally {
      setBusyId(null);
    }
  }

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <Text style={styles.title}>Available jobs</Text>
        <Text style={styles.subtitle}>Fresh offers, ranked for you.</Text>
      </View>

      {message ? (
        <View style={styles.banner} testID="jobs-banner">
          <Text style={styles.bannerText}>{message}</Text>
        </View>
      ) : null}

      {loading ? (
        <View style={styles.loading}>
          <ActivityIndicator color={colors.primary} />
        </View>
      ) : (
        <ScrollView
          contentContainerStyle={styles.list}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />
          }
        >
          {offers.length === 0 ? (
            <EmptyState
              testID="jobs-empty"
              title="No pending offers"
              hint="Pull down to refresh. Keep availability on — new offers arrive throughout the day."
            />
          ) : (
            offers.map((o) => (
              <Card key={o.id} style={styles.card} testID={`offer-card-${o.id}`}>
                <View style={styles.cardHeader}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.skill}>{o.job.skill.replace('_', ' ')}</Text>
                    <Text style={styles.project} numberOfLines={1}>
                      {o.job.project.name}
                    </Text>
                  </View>
                  <View style={styles.wageBox}>
                    <Text style={styles.wageAmt}>₹{o.job.dailyWage}</Text>
                    <Text style={styles.wageDay}>per day</Text>
                  </View>
                </View>

                <View style={styles.metaRow}>
                  <View style={styles.metaItem}>
                    <Ionicons name="location" size={13} color={colors.textDim} />
                    <Text style={styles.metaText}>{o.distanceKm.toFixed(1)} km</Text>
                  </View>
                  <View style={styles.metaItem}>
                    <Ionicons name="time" size={13} color={colors.textDim} />
                    <Text style={styles.metaText}>
                      {o.job.startTime}–{o.job.endTime}
                    </Text>
                  </View>
                  <View style={styles.metaItem}>
                    <Ionicons name="calendar" size={13} color={colors.textDim} />
                    <Text style={styles.metaText}>
                      {new Date(o.job.shiftDate).toLocaleDateString('en-IN', {
                        weekday: 'short',
                        day: 'numeric',
                        month: 'short',
                      })}
                    </Text>
                  </View>
                </View>

                {o.job.project.contractor ? (
                  <Text style={styles.contractor} numberOfLines={1}>
                    by {o.job.project.contractor.companyName}
                  </Text>
                ) : null}

                {o.job.notes ? (
                  <Text style={styles.notes} numberOfLines={2}>
                    {o.job.notes}
                  </Text>
                ) : null}

                <View style={styles.actions}>
                  <Button
                    testID={`offer-decline-${o.id}`}
                    label="Decline"
                    variant="secondary"
                    onPress={() => decline(o)}
                    loading={busyId === o.id}
                    style={{ flex: 1 }}
                  />
                  <Button
                    testID={`offer-accept-${o.id}`}
                    label="Accept"
                    variant="primary"
                    onPress={() => accept(o)}
                    loading={busyId === o.id}
                    style={{ flex: 1 }}
                  />
                </View>

                <View style={styles.scoreRow}>
                  <Chip label={`Match ${(o.score * 100).toFixed(0)}%`} tone="primary" />
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
  banner: {
    marginHorizontal: spacing.md,
    marginBottom: spacing.sm,
    padding: spacing.md,
    backgroundColor: colors.primarySoft,
    borderColor: colors.primary,
    borderWidth: 1,
    borderRadius: radius.md,
  },
  bannerText: { color: colors.primary, fontWeight: '600' },
  loading: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  list: { padding: spacing.md, gap: spacing.md, paddingBottom: spacing.xxl },
  card: { gap: spacing.sm },
  cardHeader: { flexDirection: 'row', alignItems: 'flex-start', gap: 12 },
  skill: { color: colors.text, ...t.h2 },
  project: { color: colors.textDim, ...t.small, marginTop: 2 },
  wageBox: { alignItems: 'flex-end' },
  wageAmt: { color: colors.primary, fontSize: 24, fontWeight: '800' },
  wageDay: { color: colors.textMuted, fontSize: 11 },
  metaRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.md, marginTop: 4 },
  metaItem: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  metaText: { color: colors.textDim, fontSize: 13 },
  contractor: { color: colors.textMuted, fontSize: 12 },
  notes: { color: colors.textDim, fontSize: 13, marginTop: 4 },
  actions: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.sm },
  scoreRow: { flexDirection: 'row', justifyContent: 'flex-end' },
});
