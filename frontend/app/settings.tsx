import { ScrollView, StyleSheet, Text, View, Pressable, Linking } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';

import { useAuth } from '@/src/context/AuthContext';
import { Card } from '@/src/components/ui';
import { Button } from '@/src/components/Button';
import { colors, spacing, type as t } from '@/src/theme';

export default function Settings() {
  const router = useRouter();
  const { user, signOut } = useAuth();

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} style={styles.back} hitSlop={12} testID="settings-back">
          <Ionicons name="chevron-back" size={26} color={colors.text} />
        </Pressable>
        <Text style={styles.title}>Settings</Text>
        <View style={{ width: 34 }} />
      </View>

      <ScrollView contentContainerStyle={styles.container}>
        <Card style={{ gap: 4 }}>
          <Text style={styles.h3}>Account</Text>
          <Text style={styles.dim}>{user?.phone}</Text>
          <Text style={styles.dim}>Role: {user?.role}</Text>
        </Card>

        <Card style={{ marginTop: spacing.md, gap: spacing.sm }}>
          <Text style={styles.h3}>Permissions</Text>
          <Text style={styles.dim}>
            Location access is used for check-in/check-out and dispatching nearby jobs.
          </Text>
          <Button
            testID="settings-open-settings"
            label="Open system settings"
            variant="secondary"
            onPress={() => Linking.openSettings()}
          />
        </Card>

        <Card style={{ marginTop: spacing.md, gap: 4 }}>
          <Text style={styles.h3}>About</Text>
          <Text style={styles.dim}>Dispatch Platform · Worker App</Text>
          <Text style={styles.dim}>Version 0.1.0 (MVP)</Text>
        </Card>

        <Button
          testID="settings-signout"
          label="Sign out"
          variant="danger"
          onPress={signOut}
          style={{ marginTop: spacing.xl }}
        />
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
  h3: { color: colors.text, ...t.h3 },
  dim: { color: colors.textDim, ...t.small },
});
