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
import * as Location from 'expo-location';

import { api, ApiException } from '@/src/api/client';
import { useAuth } from '@/src/context/AuthContext';
import { Button } from '@/src/components/Button';
import { Label } from '@/src/components/ui';
import { colors, radius, spacing, type as t } from '@/src/theme';

const SKILLS: { code: string; label: string }[] = [
  { code: 'MASON', label: 'Mason' },
  { code: 'HELPER', label: 'Helper' },
  { code: 'BAR_BENDER', label: 'Bar Bender' },
  { code: 'CARPENTER', label: 'Carpenter' },
  { code: 'PAINTER', label: 'Painter' },
  { code: 'ELECTRICIAN', label: 'Electrician' },
  { code: 'PLUMBER', label: 'Plumber' },
  { code: 'WELDER', label: 'Welder' },
  { code: 'TILE_LAYER', label: 'Tile Layer' },
  { code: 'SUPERVISOR', label: 'Supervisor' },
];

export default function Register() {
  const router = useRouter();
  const { user, refreshMe } = useAuth();

  const [fullName, setFullName] = useState(user?.fullName || '');
  const [selected, setSelected] = useState<string[]>([]);
  const [experience, setExperience] = useState('2');
  const [wage, setWage] = useState('700');
  const [city, setCity] = useState('Bengaluru');
  const [state, setState] = useState('Karnataka');
  const [coords, setCoords] = useState<{ lat: number; lng: number } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function toggleSkill(code: string) {
    setSelected((s) => (s.includes(code) ? s.filter((x) => x !== code) : [...s, code]));
  }

  async function useMyLocation() {
    try {
      const perm = await Location.requestForegroundPermissionsAsync();
      if (perm.status !== 'granted') {
        setError('Location permission denied. You can still continue without it.');
        return;
      }
      const loc = await Location.getCurrentPositionAsync({});
      setCoords({ lat: loc.coords.latitude, lng: loc.coords.longitude });
    } catch {
      setError('Could not read your location right now.');
    }
  }

  async function onSubmit() {
    setError(null);
    if (!fullName.trim()) return setError('Enter your full name');
    if (selected.length === 0) return setError('Pick at least one skill');
    const exp = parseInt(experience, 10);
    const dw = parseInt(wage, 10);
    if (isNaN(exp) || exp < 0) return setError('Enter valid experience');
    if (isNaN(dw) || dw < 100) return setError('Enter valid daily wage (min ₹100)');

    setLoading(true);
    try {
      await api.completeProfile({
        fullName: fullName.trim(),
        skills: selected,
        experienceYears: exp,
        dailyWage: dw,
        city,
        state,
        homeLatitude: coords?.lat,
        homeLongitude: coords?.lng,
      });
      await refreshMe();
      router.replace('/(tabs)');
    } catch (e) {
      setError(e instanceof ApiException ? e.message : 'Could not save profile');
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
          <Text style={styles.h1}>Complete profile</Text>
          <Text style={styles.sub}>Tell us about your work so we can dispatch the right jobs.</Text>

          <Label>Full name</Label>
          <TextInput
            testID="register-name"
            style={styles.input}
            value={fullName}
            onChangeText={setFullName}
            placeholder="e.g. Rajesh Kumar"
            placeholderTextColor={colors.textMuted}
          />

          <Label style={{ marginTop: spacing.md }}>Skills</Label>
          <View style={styles.skillGrid}>
            {SKILLS.map((s) => {
              const on = selected.includes(s.code);
              return (
                <Pressable
                  key={s.code}
                  onPress={() => toggleSkill(s.code)}
                  testID={`skill-chip-${s.code}`}
                  style={[styles.skillChip, on && styles.skillChipOn]}
                >
                  {on ? <Ionicons name="checkmark" size={14} color={colors.textInverse} /> : null}
                  <Text style={[styles.skillLabel, on && styles.skillLabelOn]}>{s.label}</Text>
                </Pressable>
              );
            })}
          </View>

          <View style={styles.row2}>
            <View style={{ flex: 1 }}>
              <Label>Experience (yrs)</Label>
              <TextInput
                testID="register-experience"
                style={styles.input}
                value={experience}
                onChangeText={setExperience}
                keyboardType="number-pad"
              />
            </View>
            <View style={{ flex: 1 }}>
              <Label>Daily wage (₹)</Label>
              <TextInput
                testID="register-wage"
                style={styles.input}
                value={wage}
                onChangeText={setWage}
                keyboardType="number-pad"
              />
            </View>
          </View>

          <View style={styles.row2}>
            <View style={{ flex: 1 }}>
              <Label>City</Label>
              <TextInput
                testID="register-city"
                style={styles.input}
                value={city}
                onChangeText={setCity}
              />
            </View>
            <View style={{ flex: 1 }}>
              <Label>State</Label>
              <TextInput
                testID="register-state"
                style={styles.input}
                value={state}
                onChangeText={setState}
              />
            </View>
          </View>

          <Pressable
            testID="register-use-location"
            onPress={useMyLocation}
            style={styles.locationBtn}
          >
            <Ionicons
              name={coords ? 'checkmark-circle' : 'location-outline'}
              size={20}
              color={coords ? colors.success : colors.primary}
            />
            <Text style={styles.locationText}>
              {coords
                ? `Using your location (${coords.lat.toFixed(3)}, ${coords.lng.toFixed(3)})`
                : 'Use my current location for dispatch'}
            </Text>
          </Pressable>

          {error ? (
            <View style={styles.errorBox} testID="register-error">
              <Ionicons name="alert-circle" color={colors.danger} size={18} />
              <Text style={styles.errorText}>{error}</Text>
            </View>
          ) : null}

          <Button
            testID="register-submit"
            label="Save & continue"
            onPress={onSubmit}
            loading={loading}
            style={{ marginTop: spacing.lg }}
          />
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  container: { padding: spacing.lg, paddingBottom: spacing.xxl },
  h1: { ...t.displayLg, color: colors.text },
  sub: { ...t.body, color: colors.textDim, marginTop: 6, marginBottom: spacing.xl },
  input: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    color: colors.text,
    fontSize: 16,
    paddingVertical: 14,
    paddingHorizontal: spacing.md,
  },
  row2: { flexDirection: 'row', gap: spacing.md, marginTop: spacing.md },
  skillGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  skillChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderRadius: radius.pill,
  },
  skillChipOn: { backgroundColor: colors.primary, borderColor: colors.primary },
  skillLabel: { color: colors.text, fontWeight: '600', fontSize: 14 },
  skillLabelOn: { color: colors.textInverse },
  locationBtn: {
    marginTop: spacing.md,
    padding: spacing.md,
    borderRadius: radius.lg,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  locationText: { color: colors.text, flex: 1 },
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
});
