import { useEffect, useRef, useState } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
  Pressable,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';

import { api, ApiException } from '@/src/api/client';
import { useAuth } from '@/src/context/AuthContext';
import { Button } from '@/src/components/Button';
import { colors, radius, spacing, type as t } from '@/src/theme';

export default function Otp() {
  const router = useRouter();
  const { phone, devOtp } = useLocalSearchParams<{ phone: string; devOtp?: string }>();
  const { setSession } = useAuth();

  const [code, setCode] = useState<string>((devOtp as string) || '');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resending, setResending] = useState(false);
  const [resendCountdown, setResendCountdown] = useState(30);
  const inputRef = useRef<TextInput>(null);

  useEffect(() => {
    const iv = setInterval(() => setResendCountdown((c) => (c > 0 ? c - 1 : 0)), 1000);
    return () => clearInterval(iv);
  }, []);

  async function onVerify() {
    setError(null);
    if (code.length < 4) {
      setError('Enter the 6-digit OTP');
      return;
    }
    setLoading(true);
    try {
      const r = await api.verifyOtp(phone as string, code);
      await setSession(r.token, r.user, r.profileComplete);
      router.replace(r.profileComplete ? '/(tabs)' : '/register');
    } catch (e) {
      const msg = e instanceof ApiException ? e.message : 'Invalid OTP';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  async function onResend() {
    if (resendCountdown > 0) return;
    setResending(true);
    setError(null);
    try {
      const r = await api.requestOtp(phone as string);
      if (r.devOtp) setCode(r.devOtp);
      setResendCountdown(30);
    } catch (e) {
      setError(e instanceof ApiException ? e.message : 'Failed to resend');
    } finally {
      setResending(false);
    }
  }

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={{ flex: 1 }}
      >
        <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">
          <Pressable
            testID="otp-back"
            onPress={() => router.back()}
            style={styles.back}
            hitSlop={12}
          >
            <Ionicons name="chevron-back" size={26} color={colors.text} />
          </Pressable>

          <Text style={styles.h1}>Enter code</Text>
          <Text style={styles.sub}>
            Sent to <Text style={{ color: colors.text }}>{phone}</Text>
          </Text>

          <TextInput
            ref={inputRef}
            testID="otp-input"
            style={styles.input}
            keyboardType="number-pad"
            value={code}
            onChangeText={setCode}
            maxLength={6}
            autoFocus
            placeholder="123456"
            placeholderTextColor={colors.textMuted}
          />

          {error ? (
            <View style={styles.errorBox} testID="otp-error">
              <Ionicons name="alert-circle" color={colors.danger} size={18} />
              <Text style={styles.errorText}>{error}</Text>
            </View>
          ) : null}

          <Button
            testID="otp-verify-button"
            label="Verify & continue"
            onPress={onVerify}
            loading={loading}
            style={{ marginTop: spacing.lg }}
          />

          <Pressable onPress={onResend} disabled={resendCountdown > 0 || resending} testID="otp-resend">
            <Text
              style={[
                styles.resend,
                { color: resendCountdown > 0 ? colors.textMuted : colors.primary },
              ]}
            >
              {resendCountdown > 0
                ? `Resend OTP in ${resendCountdown}s`
                : resending
                  ? 'Sending…'
                  : 'Resend OTP'}
            </Text>
          </Pressable>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  container: { padding: spacing.lg, paddingTop: spacing.md, flexGrow: 1 },
  back: { alignSelf: 'flex-start', padding: 4, marginBottom: spacing.lg },
  h1: { ...t.displayLg, color: colors.text },
  sub: { ...t.body, color: colors.textDim, marginTop: 8, marginBottom: spacing.xl },
  input: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    color: colors.text,
    fontSize: 30,
    fontWeight: '700',
    paddingVertical: 20,
    textAlign: 'center',
    letterSpacing: 12,
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
  resend: { textAlign: 'center', marginTop: spacing.lg, fontWeight: '600' },
});
