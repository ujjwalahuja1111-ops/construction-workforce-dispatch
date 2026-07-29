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

import { api } from '@/src/api/client';
import { Card, EmptyState } from '@/src/components/ui';
import { colors, spacing, type as t } from '@/src/theme';

export default function Notifications() {
  const router = useRouter();
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await api.notifications();
      setItems(r.notifications);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    api.markAllRead().catch(() => {});
  }, [load]);

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} style={styles.back} hitSlop={12} testID="notif-back">
          <Ionicons name="chevron-back" size={26} color={colors.text} />
        </Pressable>
        <Text style={styles.title}>Notifications</Text>
        <View style={{ width: 34 }} />
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
          {items.length === 0 ? (
            <EmptyState
              testID="notifications-empty"
              title="Nothing here yet"
              hint="Job offers and shift updates will appear here."
            />
          ) : (
            items.map((n) => (
              <Card
                key={n.id}
                style={[styles.card, !n.readAt ? styles.cardUnread : null]}
                testID={`notif-${n.id}`}
              >
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                  <Ionicons
                    name={n.type === 'JOB_OFFER' ? 'briefcase' : 'notifications'}
                    size={20}
                    color={colors.primary}
                  />
                  <Text style={styles.type}>{n.type.replace('_', ' ')}</Text>
                  <Text style={styles.time}>
                    {new Date(n.createdAt).toLocaleTimeString('en-IN', {
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </Text>
                </View>
                <Text style={styles.body}>{n.title}</Text>
                <Text style={styles.dim}>{n.body}</Text>
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
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    justifyContent: 'space-between',
  },
  back: { padding: 4 },
  title: { color: colors.text, ...t.h2 },
  loading: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  container: { padding: spacing.md, paddingBottom: spacing.xxl },
  card: { marginBottom: spacing.sm, gap: 4 },
  cardUnread: { borderColor: colors.primary },
  type: { color: colors.textDim, fontSize: 11, fontWeight: '800', letterSpacing: 0.5 },
  time: { color: colors.textMuted, fontSize: 11, marginLeft: 'auto' as any },
  body: { color: colors.text, ...t.bodyBold, marginTop: 6 },
  dim: { color: colors.textDim, ...t.small },
});
