import { useCallback, useEffect, useState } from 'react';
import {
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';

import { api } from '@/src/api/client';
import { useAuth } from '@/src/context/AuthContext';
import { Card, Chip, StatTile, SectionHeader, EmptyState } from '@/src/components/ui';
import { Button } from '@/src/components/Button';
import { colors, radius, spacing, type as t } from '@/src/theme';

export default function Home() {
  const router = useRouter();
  const { user, worker, refreshMe, signOut } = useAuth();
  const [offers, setOffers] = useState<any[]>([]);
  const [activeShift, setActiveShift] = useState<any | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [available, setAvailable] = useState(worker?.isAvailable ?? true);
  const [togglingAvail, setTogglingAvail] = useState(false);

  const load = useCallback(async () => {
    try {
      const [o, a] = await Promise.all([api.offers(), api.activeShift()]);
      setOffers(o.offers);
      setActiveShift(a.shift);
    } catch (e) {
      // best-effort; ui remains usable
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (worker) setAvailable(worker.isAvailable);
  }, [worker]);

  async function onRefresh() {
    setRefreshing(true);
    await Promise.all([load(), refreshMe()]);
    setRefreshing(false);
  }

  async function toggleAvailability(next: boolean) {
    setAvailable(next);
    setTogglingAvail(true);
    try {
      await api.setAvailability(next);
      await refreshMe();
    } catch {
      setAvailable(!next);
    } finally {
      setTogglingAvail(false);
    }
  }

  const trust = worker?.trustScore ?? 0;
  const trustTone: 'success' | 'warning' | 'danger' =
    trust >= 80 ? 'success' : trust >= 60 ? 'warning' : 'danger';

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <ScrollView
        contentContainerStyle={styles.container}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />}
      >
        {/* Header */}
        <View style={styles.header}>
          <View style={{ flex: 1 }}>
            <Text style={styles.hello}>Namaste,</Text>
            <Text style={styles.name} numberOfLines={1}>
              {user?.fullName || 'Worker'}
            </Text>
          </View>
          <Pressable
            testID="home-notifications"
            onPress={() => router.push('/notifications')}
            style={styles.iconBtn}
          >
            <Ionicons name="notifications-outline" size={22} color={colors.text} />
          </Pressable>
        </View>

        {/* Availability toggle */}
        <Card style={styles.availCard} testID="home-availability-card">
          <View style={{ flex: 1 }}>
            <Text style={styles.availTitle}>
              {available ? 'Available for work' : 'Off duty'}
            </Text>
            <Text style={styles.availSub}>
              {available
                ? 'Contractors can send you job offers.'
                : 'You will not receive new offers until you turn this on.'}
            </Text>
          </View>
          <Switch
            testID="home-availability-switch"
            value={available}
            onValueChange={toggleAvailability}
            disabled={togglingAvail}
            trackColor={{ true: colors.primary, false: colors.surfaceAlt }}
            thumbColor={colors.text}
          />
        </Card>

        {/* Trust score */}
        <Pressable onPress={() => router.push('/trust')} testID="home-trust-card">
          <Card style={styles.trustCard}>
            <View style={{ flex: 1 }}>
              <Text style={styles.trustLabel}>Trust score</Text>
              <View style={styles.trustRow}>
                <Text style={styles.trustValue}>{trust}</Text>
                <Text style={styles.trustOf}>/100</Text>
                <Chip label={trust >= 80 ? 'Excellent' : trust >= 60 ? 'Good' : 'Low'} tone={trustTone} />
              </View>
              <Text style={styles.trustHint}>Higher trust = more job offers.</Text>
            </View>
            <Ionicons name="chevron-forward" size={22} color={colors.textMuted} />
          </Card>
        </Pressable>

        {/* Active shift banner */}
        {activeShift ? (
          <Pressable
            onPress={() => router.push({ pathname: '/shift/[id]', params: { id: activeShift.id } })}
            testID="home-active-shift"
          >
            <Card style={styles.activeCard}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                <View style={styles.pulseDot} />
                <Text style={styles.activeLabel}>ACTIVE SHIFT</Text>
              </View>
              <Text style={styles.activeName}>{activeShift.job.project.name}</Text>
              <Text style={styles.activeMeta}>
                {activeShift.job.skill.replace('_', ' ')} · ₹{activeShift.wageAmount}
              </Text>
              <View style={styles.activeFooter}>
                <Chip label={activeShift.state.replace('_', ' ')} tone="primary" />
                <Text style={styles.activeCta}>Manage →</Text>
              </View>
            </Card>
          </Pressable>
        ) : null}

        {/* Stats */}
        <SectionHeader title="This week" />
        <View style={{ flexDirection: 'row', gap: spacing.md }}>
          <StatTile
            testID="home-stat-shifts"
            label="Shifts"
            value={String(worker?.totalShifts ?? 0)}
            hint={`${worker?.completedShifts ?? 0} completed`}
          />
          <StatTile
            testID="home-stat-earnings"
            label="Earnings"
            value={`₹${(worker?.totalEarnings ?? 0).toLocaleString('en-IN')}`}
            hint="all-time"
          />
        </View>

        {/* Offers preview */}
        <SectionHeader
          title="Available offers"
          right={
            offers.length > 0 ? (
              <Pressable onPress={() => router.push('/(tabs)/jobs')} hitSlop={8}>
                <Text style={styles.viewAll}>View all →</Text>
              </Pressable>
            ) : null
          }
        />
        {offers.length === 0 ? (
          <EmptyState
            testID="home-offers-empty"
            title="No offers right now"
            hint="Keep availability on. Fresh offers show up here as soon as they arrive."
          />
        ) : (
          offers.slice(0, 2).map((o) => (
            <Pressable
              key={o.id}
              testID={`home-offer-${o.id}`}
              onPress={() => router.push('/(tabs)/jobs')}
              style={{ marginBottom: spacing.sm }}
            >
              <Card>
                <View style={styles.offerRow}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.offerSkill}>{o.job.skill.replace('_', ' ')}</Text>
                    <Text style={styles.offerProject} numberOfLines={1}>
                      {o.job.project.name} · {o.distanceKm.toFixed(1)} km
                    </Text>
                  </View>
                  <View style={{ alignItems: 'flex-end' }}>
                    <Text style={styles.offerWage}>₹{o.job.dailyWage}</Text>
                    <Text style={styles.offerDay}>per day</Text>
                  </View>
                </View>
              </Card>
            </Pressable>
          ))
        )}

        {/* footer signout for dev convenience */}
        <View style={{ marginTop: spacing.xxl }}>
          <Button
            testID="home-signout"
            label="Sign out"
            variant="secondary"
            onPress={signOut}
          />
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  container: { padding: spacing.md, paddingBottom: spacing.xxl },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: spacing.lg,
    marginTop: spacing.sm,
  },
  hello: { color: colors.textDim, fontSize: 13 },
  name: { color: colors.text, ...t.h1, marginTop: 2 },
  iconBtn: {
    width: 42,
    height: 42,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radius.pill,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
  },
  availCard: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
  },
  availTitle: { color: colors.text, ...t.h3 },
  availSub: { color: colors.textDim, ...t.small, marginTop: 4 },
  trustCard: {
    marginTop: spacing.md,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
  },
  trustLabel: { color: colors.textDim, fontSize: 12, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5 },
  trustRow: { flexDirection: 'row', alignItems: 'flex-end', gap: 8, marginTop: 4 },
  trustValue: { color: colors.text, fontSize: 40, fontWeight: '800', lineHeight: 42 },
  trustOf: { color: colors.textMuted, fontSize: 16, marginBottom: 6 },
  trustHint: { color: colors.textMuted, fontSize: 12, marginTop: 4 },
  activeCard: {
    marginTop: spacing.md,
    backgroundColor: colors.primarySoft,
    borderColor: colors.primary,
  },
  pulseDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.primary },
  activeLabel: { color: colors.primary, fontSize: 11, fontWeight: '800', letterSpacing: 0.8 },
  activeName: { color: colors.text, ...t.h2, marginTop: 6 },
  activeMeta: { color: colors.textDim, ...t.small, marginTop: 2 },
  activeFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: spacing.md,
  },
  activeCta: { color: colors.primary, fontWeight: '700' },
  viewAll: { color: colors.primary, fontWeight: '700', fontSize: 13 },
  offerRow: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  offerSkill: { color: colors.text, ...t.h3 },
  offerProject: { color: colors.textDim, ...t.small, marginTop: 2 },
  offerWage: { color: colors.primary, fontSize: 20, fontWeight: '800' },
  offerDay: { color: colors.textMuted, fontSize: 11 },
});
