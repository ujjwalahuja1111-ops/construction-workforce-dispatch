import { ScrollView, StyleSheet, Text, View, Pressable } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';

import { useAuth } from '@/src/context/AuthContext';
import { Card, Chip } from '@/src/components/ui';
import { Button } from '@/src/components/Button';
import { colors, radius, spacing, type as t } from '@/src/theme';

export default function Profile() {
  const router = useRouter();
  const { user, worker, signOut } = useAuth();
  const skills = (worker?.skills as string | undefined)?.split(',').filter(Boolean) || [];

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <ScrollView contentContainerStyle={styles.container}>
        <View style={styles.header}>
          <View style={styles.avatar}>
            <Text style={styles.avatarText}>
              {(user?.fullName || 'W').split(' ').map((w: string) => w[0]).slice(0, 2).join('')}
            </Text>
          </View>
          <Text style={styles.name}>{user?.fullName}</Text>
          <Text style={styles.phone}>{user?.phone}</Text>
        </View>

        <Card style={{ gap: spacing.md }} testID="profile-details">
          <Row icon="briefcase" label="Skills">
            <View style={styles.chipRow}>
              {skills.length ? (
                skills.map((s) => <Chip key={s} label={s.replace('_', ' ')} tone="primary" />)
              ) : (
                <Text style={styles.dim}>No skills selected</Text>
              )}
            </View>
          </Row>
          <Divider />
          <Row icon="ribbon" label="Experience">
            <Text style={styles.value}>{worker?.experienceYears ?? 0} years</Text>
          </Row>
          <Divider />
          <Row icon="cash" label="Daily wage">
            <Text style={styles.value}>₹{worker?.dailyWage?.toLocaleString('en-IN') ?? 0}</Text>
          </Row>
          <Divider />
          <Row icon="location" label="Location">
            <Text style={styles.value}>
              {worker?.city}, {worker?.state}
            </Text>
          </Row>
        </Card>

        <Pressable onPress={() => router.push('/trust')} testID="profile-trust-link">
          <Card style={styles.navRow}>
            <Ionicons name="shield-checkmark" size={22} color={colors.primary} />
            <View style={{ flex: 1 }}>
              <Text style={styles.navTitle}>Trust score</Text>
              <Text style={styles.navSub}>See what drives your dispatch priority</Text>
            </View>
            <Ionicons name="chevron-forward" size={20} color={colors.textMuted} />
          </Card>
        </Pressable>

        <Pressable onPress={() => router.push('/settings')} testID="profile-settings-link">
          <Card style={styles.navRow}>
            <Ionicons name="settings" size={22} color={colors.text} />
            <View style={{ flex: 1 }}>
              <Text style={styles.navTitle}>Settings</Text>
              <Text style={styles.navSub}>Notifications, permissions & about</Text>
            </View>
            <Ionicons name="chevron-forward" size={20} color={colors.textMuted} />
          </Card>
        </Pressable>

        <Button
          testID="profile-signout"
          label="Sign out"
          variant="secondary"
          onPress={signOut}
          style={{ marginTop: spacing.lg }}
        />
      </ScrollView>
    </SafeAreaView>
  );
}

function Row({ icon, label, children }: { icon: any; label: string; children: React.ReactNode }) {
  return (
    <View style={styles.rowItem}>
      <Ionicons name={icon} size={18} color={colors.textDim} />
      <View style={{ flex: 1 }}>
        <Text style={styles.rowLabel}>{label}</Text>
        <View style={{ marginTop: 4 }}>{children}</View>
      </View>
    </View>
  );
}
function Divider() {
  return <View style={{ height: 1, backgroundColor: colors.divider }} />;
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  container: { padding: spacing.md, paddingBottom: spacing.xxl },
  header: { alignItems: 'center', paddingVertical: spacing.lg },
  avatar: {
    width: 84,
    height: 84,
    borderRadius: 42,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.md,
  },
  avatarText: { color: colors.textInverse, fontSize: 30, fontWeight: '800' },
  name: { color: colors.text, ...t.h1 },
  phone: { color: colors.textDim, ...t.body, marginTop: 4 },
  rowItem: { flexDirection: 'row', gap: 12, alignItems: 'flex-start' },
  rowLabel: { color: colors.textDim, fontSize: 12, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5 },
  value: { color: colors.text, ...t.bodyBold },
  dim: { color: colors.textMuted },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  navRow: {
    marginTop: spacing.md,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
  },
  navTitle: { color: colors.text, ...t.bodyBold },
  navSub: { color: colors.textDim, ...t.small, marginTop: 2 },
});
