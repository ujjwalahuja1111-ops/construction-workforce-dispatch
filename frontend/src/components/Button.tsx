import { ActivityIndicator, Pressable, StyleSheet, Text, ViewStyle, StyleProp } from 'react-native';
import { colors, radius, touch, type as t } from '../theme';

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'success';

export function Button({
  label,
  onPress,
  variant = 'primary',
  loading,
  disabled,
  style,
  testID,
}: {
  label: string;
  onPress: () => void;
  variant?: Variant;
  loading?: boolean;
  disabled?: boolean;
  style?: StyleProp<ViewStyle>;
  testID?: string;
}) {
  const isDisabled = !!(disabled || loading);

  const bg: Record<Variant, string> = {
    primary:   colors.primary,
    secondary: colors.surfaceAlt,
    ghost:     'transparent',
    danger:    colors.danger,
    success:   colors.success,
  };
  const fg: Record<Variant, string> = {
    primary:   colors.textInverse,
    secondary: colors.text,
    ghost:     colors.text,
    danger:    '#FFFFFF',
    success:   '#052610',
  };
  const border: Record<Variant, string> = {
    primary:   colors.primary,
    secondary: colors.border,
    ghost:     colors.border,
    danger:    colors.danger,
    success:   colors.success,
  };

  return (
    <Pressable
      testID={testID}
      accessibilityRole="button"
      onPress={onPress}
      disabled={isDisabled}
      style={({ pressed }) => [
        styles.btn,
        {
          backgroundColor: bg[variant],
          borderColor: border[variant],
          opacity: isDisabled ? 0.5 : pressed ? 0.85 : 1,
        },
        style,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={fg[variant]} />
      ) : (
        <Text style={[t.bodyBold, { color: fg[variant] }]}>{label}</Text>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  btn: {
    minHeight: touch.minHeight,
    borderRadius: radius.lg,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 20,
    flexDirection: 'row',
  },
});
