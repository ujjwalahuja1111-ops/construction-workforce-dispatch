import { Redirect } from 'expo-router';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';
import { useAuth } from '@/src/context/AuthContext';
import { colors, spacing } from '@/src/theme';

// Splash / initial redirect. The AuthContext bootstraps on mount; while it
// loads we show a branded spinner. Once loaded we redirect to the right root:
//   - not signed in       → /login
//   - signed in, no profile → /register
//   - signed in, complete   → /(tabs)
export default function Index() {
  const { loading, token, profileComplete } = useAuth();

  if (loading) {
    return (
      <View style={styles.container} testID="splash-screen">
        <View style={styles.logoBadge}>
          <Text style={styles.logoText}>DP</Text>
        </View>
        <Text style={styles.title}>Dispatch</Text>
        <Text style={styles.subtitle}>Work. Anywhere. Anytime.</Text>
        <ActivityIndicator color={colors.primary} style={{ marginTop: 32 }} />
      </View>
    );
  }

  if (!token) return <Redirect href="/login" />;
  if (!profileComplete) return <Redirect href="/register" />;
  return <Redirect href="/(tabs)" />;
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.bg,
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.xl,
  },
  logoBadge: {
    width: 84,
    height: 84,
    backgroundColor: colors.primary,
    borderRadius: 24,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.lg,
  },
  logoText: {
    color: colors.textInverse,
    fontSize: 36,
    fontWeight: '900',
    letterSpacing: -1,
  },
  title: {
    color: colors.text,
    fontSize: 32,
    fontWeight: '800',
    letterSpacing: -0.5,
  },
  subtitle: {
    color: colors.textDim,
    fontSize: 15,
    marginTop: 6,
  },
});
