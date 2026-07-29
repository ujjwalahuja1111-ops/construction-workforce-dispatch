import { useState } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';

import { api, ApiException } from '@/src/api/client';
import { Button } from '@/src/components/Button';
import { colors, radius, spacing, type as t } from '@/src/theme';

export default function Login() {
  const router = useRouter();
  const [phone, setPhone] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onContinue() {
    setError(null);
    const digits = phone.replace(/\D/g, '').slice(-10);
    if (digits.length !== 10) {
      setError('Enter a valid 10-digit phone number');
      return;
    }
    setLoading(true);
    try {
      const r = await api.requestOtp(`+91${digits}`);
      router.push({
        pathname: '/otp',
        params: { phone: `+91${digits}`, devOtp: r.devOtp ?? '' },
      });
    } catch (e) {
      const msg = e instanceof ApiException ? e.message : 'Something went wrong';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={{ flex: 1 }}
      >
        <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">
          <View style={styles.logoBadge}>
            <Text style={styles.logoText}>DP</Text>
          </View>

          <Text style={styles.h1}>Sign in</Text>
          <Text style={styles.sub}>
            Enter your mobile number. We&apos;ll send a one-time code.
          </Text>

          <View style={styles.inputWrap}>
            <View style={styles.prefix}>
              <Text style={styles.prefixText}>+91</Text>
            </View>
            <TextInput
              testID="phone-input"
              style={styles.input}
              placeholder="Mobile number"
              placeholderTextColor={colors.textMuted}
              keyboardType="phone-pad"
              value={phone}
              onChangeText={setPhone}
              maxLength={13}
              autoFocus
            />
          </View>

          {error ? (
            <View style={styles.errorBox} testID="login-error">
              <Ionicons name="alert-circle" color={colors.danger} size={18} />
              <Text style={styles.errorText}>{error}</Text>
            </View>
          ) : null}

          <Button
            testID="login-continue-button"
            label="Send OTP"
            onPress={onContinue}
            loading={loading}
            style={{ marginTop: spacing.lg }}
          />

          <Text style={styles.hint}>
            Development mode — OTP is <Text style={styles.hintCode}>123456</Text>.
          </Text>

          <Pressable
            testID="login-quick-worker"
            onPress={() => setPhone('9020001000')}
            style={{ marginTop: spacing.md }}
          >
            <Text style={styles.demoLink}>Use demo worker · 9020001000</Text>
          </Pressable>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  container: { padding: spacing.lg, paddingTop: spacing.xxl, flexGrow: 1 },
  logoBadge: {
    width: 60,
    height: 60,
    backgroundColor: colors.primary,
    borderRadius: 18,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.xl,
  },
  logoText: { color: colors.textInverse, fontSize: 26, fontWeight: '900' },
  h1: { ...t.displayLg, color: colors.text },
  sub: { ...t.body, color: colors.textDim, marginTop: 8, marginBottom: spacing.xl },
  inputWrap: {
    flexDirection: 'row',
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    overflow: 'hidden',
  },
  prefix: {
    paddingHorizontal: spacing.md,
    justifyContent: 'center',
    backgroundColor: colors.surfaceAlt,
  },
  prefixText: { color: colors.text, fontSize: 16, fontWeight: '600' },
  input: {
    flex: 1,
    color: colors.text,
    fontSize: 18,
    paddingVertical: 16,
    paddingHorizontal: spacing.md,
    letterSpacing: 1,
  },
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
  hint: { color: colors.textMuted, ...t.small, textAlign: 'center', marginTop: spacing.lg },
  hintCode: { color: colors.primary, fontWeight: '700' },
  demoLink: { color: colors.primary, textAlign: 'center', fontWeight: '600' },
});
