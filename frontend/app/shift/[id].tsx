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
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import * as Location from 'expo-location';

import { api, ApiException } from '@/src/api/client';
import { Card, Chip } from '@/src/components/ui';
import { Button } from '@/src/components/Button';
import { colors, radius, spacing, type as t } from '@/src/theme';

// Map current state → the single next action (label + api action + geo needed)
const NEXT_ACTION: Record<
  string,
  { label: string; action: any; variant: any; needsGeo?: boolean } | null
> = {
  ACCEPTED:   { label: 'Start travelling',      action: 'travel',      variant: 'primary' },
  TRAVELLING: { label: 'I have arrived',         action: 'arrive',      variant: 'primary' },
  ARRIVED:    { label: 'Check in',               action: 'check-in',    variant: 'primary', needsGeo: true },
  CHECKED_IN: { label: 'Start work',             action: 'start-work',  variant: 'primary' },
  WORKING:    { label: 'Take a break',           action: 'break',       variant: 'secondary' },
  BREAK:      { label: 'Resume work',            action: 'resume',      variant: 'primary' },
  RESUMED:    { label: 'Finish work',            action: 'complete',    variant: 'primary' },
  COMPLETED:  { label: 'Check out',              action: 'check-out',   variant: 'primary', needsGeo: true },
  CHECKED_OUT:{ label: 'Close shift',            action: 'close',       variant: 'success' },
  CLOSED:     null,
  CANCELLED:  null,
};

// Secondary action for WORKING → straight to COMPLETED (skip break)
const SECONDARY_ACTION: Record<
  string,
  { label: string; action: any; variant: any } | null
> = {
  WORKING: { label: 'Finish work', action: 'complete', variant: 'success' },
  RESUMED: { label: 'Take a break', action: 'break', variant: 'secondary' },
};

export default function ShiftDetail() {
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [shift, setShift] = useState<any | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await api.getShift(id);
      setShift(r.shift);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  async function doAction(action: string, needsGeo?: boolean) {
    setBusy(true);
    setError(null);
    try {
      let body: any = {};
      if (needsGeo) {
        const perm = await Location.requestForegroundPermissionsAsync();
        if (perm.status !== 'granted') {
          throw new Error('Location permission is required for check-in/out');
        }
        const loc = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High });
        body = { latitude: loc.coords.latitude, longitude: loc.coords.longitude };
      }
      await api.shiftAction(id, action as any, body);
      await load();
    } catch (e) {
      const msg = e instanceof ApiException ? e.message : e instanceof Error ? e.message : 'Action failed';
      setError(msg);
    } finally {
      setBusy(false);
    }
  }

  if (loading || !shift) {
    return (
      <SafeAreaView style={styles.safe}>
        <View style={styles.loading}>
          <ActivityIndicator color={colors.primary} />
        </View>
      </SafeAreaView>
    );
  }

  const nextAction = NEXT_ACTION[shift.state];
  const secondary = SECONDARY_ACTION[shift.state];
  const isTerminal = shift.state === 'CLOSED' || shift.state === 'CANCELLED';

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} style={styles.back} hitSlop={12} testID="shift-back">
          <Ionicons name="chevron-back" size={26} color={colors.text} />
        </Pressable>
        <Text style={styles.title}>Shift</Text>
        <View style={{ width: 34 }} />
      </View>

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
        {/* Big state banner */}
        <Card style={styles.stateCard} testID="shift-state-card">
          <Text style={styles.stateLabel}>Current status</Text>
          <Text style={styles.stateValue}>{shift.state.replace('_', ' ')}</Text>
          <View style={styles.chipRow}>
            <Chip label={shift.job.skill.replace('_', ' ')} tone="primary" />
            <Chip
              label={`₹${shift.wageAmount}`}
              tone="success"
            />
          </View>
        </Card>

        {/* Project details */}
        <Card style={{ marginTop: spacing.md, gap: 8 }} testID="shift-project-card">
          <Text style={styles.h3}>{shift.job.project.name}</Text>
          <Text style={styles.dim}>{shift.job.project.siteAddress}</Text>
          <Text style={styles.dim}>
            {shift.job.project.city}, {shift.job.project.state}
          </Text>
          <View style={styles.hLine} />
          <View style={styles.metaGrid}>
            <MetaCol
              icon="calendar"
              label="Date"
              value={new Date(shift.shiftDate).toLocaleDateString('en-IN', {
                weekday: 'short',
                day: 'numeric',
                month: 'short',
              })}
            />
            <MetaCol
              icon="time"
              label="Hours"
              value={`${shift.scheduledStart} – ${shift.scheduledEnd}`}
            />
            {shift.job.project.contractor ? (
              <MetaCol
                icon="business"
                label="Contractor"
                value={shift.job.project.contractor.companyName}
              />
            ) : null}
          </View>
        </Card>

        {/* Attendance details */}
        {(shift.checkInAt || shift.checkOutAt) ? (
          <Card style={{ marginTop: spacing.md, gap: 8 }} testID="shift-attendance-card">
            <Text style={styles.h3}>Attendance</Text>
            {shift.checkInAt ? (
              <Text style={styles.body}>
                Checked in at{' '}
                <Text style={styles.bodyStrong}>
                  {new Date(shift.checkInAt).toLocaleTimeString('en-IN', {
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </Text>
                {shift.lateMinutes > 0 ? (
                  <Text style={{ color: colors.warning }}> ({shift.lateMinutes}m late)</Text>
                ) : null}
              </Text>
            ) : null}
            {shift.checkOutAt ? (
              <Text style={styles.body}>
                Checked out at{' '}
                <Text style={styles.bodyStrong}>
                  {new Date(shift.checkOutAt).toLocaleTimeString('en-IN', {
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </Text>
                {shift.earlyExitMinutes > 0 ? (
                  <Text style={{ color: colors.warning }}> ({shift.earlyExitMinutes}m early)</Text>
                ) : null}
              </Text>
            ) : null}
            {shift.workedMinutes ? (
              <Text style={styles.body}>
                Worked{' '}
                <Text style={styles.bodyStrong}>
                  {Math.floor(shift.workedMinutes / 60)}h {shift.workedMinutes % 60}m
                </Text>
              </Text>
            ) : null}
            {shift.amountEarned ? (
              <Text style={styles.body}>
                Earned <Text style={{ color: colors.primary, fontWeight: '800' }}>₹{shift.amountEarned}</Text>
              </Text>
            ) : null}
          </Card>
        ) : null}

        {/* Timeline */}
        <Text style={[styles.h3, { marginTop: spacing.lg }]}>Timeline</Text>
        <View style={styles.timeline}>
          {(shift.events || []).map((ev: any, i: number) => (
            <View key={ev.id || i} style={styles.tlItem}>
              <View style={styles.tlDot} />
              {i < shift.events.length - 1 ? <View style={styles.tlLine} /> : null}
              <View style={{ flex: 1 }}>
                <Text style={styles.tlTo}>{ev.toState.replace('_', ' ')}</Text>
                <Text style={styles.tlTime}>
                  {new Date(ev.createdAt).toLocaleTimeString('en-IN', {
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                  {ev.note ? ` · ${ev.note}` : ''}
                </Text>
              </View>
            </View>
          ))}
        </View>

        {error ? (
          <View style={styles.errorBox} testID="shift-error">
            <Ionicons name="alert-circle" color={colors.danger} size={18} />
            <Text style={styles.errorText}>{error}</Text>
          </View>
        ) : null}
      </ScrollView>

      {!isTerminal && nextAction ? (
        <View style={styles.footer}>
          {secondary ? (
            <Button
              testID="shift-secondary-action"
              label={secondary.label}
              variant={secondary.variant}
              onPress={() => doAction(secondary.action)}
              loading={busy}
              style={{ flex: 1 }}
            />
          ) : null}
          <Button
            testID="shift-primary-action"
            label={nextAction.label}
            variant={nextAction.variant}
            onPress={() => doAction(nextAction.action, nextAction.needsGeo)}
            loading={busy}
            style={{ flex: secondary ? 1.4 : 1 }}
          />
        </View>
      ) : null}
    </SafeAreaView>
  );
}

function MetaCol({ icon, label, value }: { icon: any; label: string; value: string }) {
  return (
    <View style={styles.metaCol}>
      <View style={styles.metaHead}>
        <Ionicons name={icon} size={13} color={colors.textDim} />
        <Text style={styles.metaLabel}>{label}</Text>
      </View>
      <Text style={styles.metaVal} numberOfLines={2}>
        {value}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  loading: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    justifyContent: 'space-between',
  },
  back: { padding: 4 },
  title: { color: colors.text, ...t.h2 },
  container: { padding: spacing.md, paddingBottom: 140 },
  stateCard: {
    backgroundColor: colors.primarySoft,
    borderColor: colors.primary,
  },
  stateLabel: { color: colors.primary, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.6 },
  stateValue: { color: colors.text, fontSize: 34, fontWeight: '800', marginTop: 4 },
  chipRow: { flexDirection: 'row', gap: 6, marginTop: spacing.sm, flexWrap: 'wrap' },
  h3: { color: colors.text, ...t.h3 },
  dim: { color: colors.textDim, ...t.small },
  body: { color: colors.text, ...t.body },
  bodyStrong: { color: colors.text, fontWeight: '700' },
  hLine: { height: 1, backgroundColor: colors.divider, marginVertical: 8 },
  metaGrid: { flexDirection: 'row', gap: spacing.md, flexWrap: 'wrap' },
  metaCol: { minWidth: 100, gap: 4 },
  metaHead: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  metaLabel: { color: colors.textDim, fontSize: 11, fontWeight: '700', textTransform: 'uppercase' },
  metaVal: { color: colors.text, ...t.bodyBold },
  timeline: { marginTop: spacing.sm },
  tlItem: { flexDirection: 'row', gap: 12, paddingLeft: 4, position: 'relative', paddingBottom: spacing.md },
  tlDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
    backgroundColor: colors.primary,
    marginTop: 6,
    zIndex: 1,
  },
  tlLine: {
    position: 'absolute',
    left: 8,
    top: 16,
    bottom: 0,
    width: 2,
    backgroundColor: colors.border,
  },
  tlTo: { color: colors.text, ...t.bodyBold },
  tlTime: { color: colors.textDim, fontSize: 12, marginTop: 2 },
  errorBox: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginTop: spacing.md,
    padding: spacing.md,
    backgroundColor: colors.dangerSoft,
    borderRadius: radius.md,
  },
  errorText: { color: colors.danger, ...t.small, flex: 1 },
  footer: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    padding: spacing.md,
    paddingBottom: spacing.lg,
    backgroundColor: colors.bg,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    flexDirection: 'row',
    gap: spacing.sm,
  },
});
