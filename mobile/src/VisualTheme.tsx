import React, { createContext, ReactNode, useContext, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Pressable,
  ScrollView,
  Text,
  TextInput,
  View,
} from 'react-native';

import {
  VisualTheme,
  fetchVisualTheme,
  resetVisualTheme,
  saveVisualTheme,
} from './api';

export const DEFAULT_VISUAL_THEME: VisualTheme = {
  accent: '#2d92ff',
  accent_soft: '#8ac5ff',
  background: '#02060a',
  panel: '#08121c',
  panel_alt: '#0b1824',
  border: '#1f3447',
  text: '#f7fbff',
  muted: '#92a0ad',
  success: '#45d47b',
  danger: '#ff7880',
  warning: '#ffc36f',
  topbar: '#03080d',
  card_radius: 18,
  button_radius: 12,
  content_padding: 16,
  panel_opacity: 0.80,
  image_opacity: 0.88,
  shade_opacity: 0.24,
  compact: false,
};

type ThemeContextValue = {
  theme: VisualTheme;
  loading: boolean;
  refresh: () => Promise<void>;
  save: (theme: VisualTheme) => Promise<VisualTheme>;
  reset: () => Promise<VisualTheme>;
};

const ThemeContext = createContext<ThemeContextValue>({
  theme: DEFAULT_VISUAL_THEME,
  loading: false,
  refresh: async () => undefined,
  save: async theme => theme,
  reset: async () => DEFAULT_VISUAL_THEME,
});

export function rgba(hex: string, alpha: number) {
  const normalized = /^#[0-9a-f]{6}$/i.test(hex) ? hex.slice(1) : '02060a';
  const r = parseInt(normalized.slice(0, 2), 16);
  const g = parseInt(normalized.slice(2, 4), 16);
  const b = parseInt(normalized.slice(4, 6), 16);
  const a = Math.max(0, Math.min(1, Number(alpha) || 0));
  return `rgba(${r},${g},${b},${a})`;
}

let ACTIVE_VISUAL_THEME: VisualTheme = DEFAULT_VISUAL_THEME;

export function getActiveVisualTheme() {
  return ACTIVE_VISUAL_THEME;
}

export function visualCardStyle(variant: 'panel' | 'alt' = 'panel') {
  const theme = ACTIVE_VISUAL_THEME;
  const source = variant === 'alt' ? theme.panel_alt : theme.panel;
  return {
    backgroundColor: rgba(source, theme.panel_opacity),
    borderColor: theme.border,
    borderRadius: theme.card_radius,
  };
}

export function visualInputStyle() {
  const theme = ACTIVE_VISUAL_THEME;
  return {
    backgroundColor: rgba(theme.background, 0.76),
    borderColor: theme.border,
    borderRadius: theme.button_radius,
    color: theme.text,
  };
}

export function visualContentStyle() {
  const theme = ACTIVE_VISUAL_THEME;
  return {
    padding: theme.content_padding,
    gap: theme.compact ? 8 : 11,
  };
}

export function visualButtonStyle(kind: 'blue' | 'green' | 'red' | 'ghost' = 'blue') {
  const theme = ACTIVE_VISUAL_THEME;
  return {
    backgroundColor:
      kind === 'green' ? theme.success :
      kind === 'red' ? theme.danger :
      kind === 'ghost' ? rgba(theme.panel_alt, 0.88) :
      theme.accent,
    borderColor: kind === 'ghost' ? theme.border : undefined,
    borderRadius: theme.button_radius,
  };
}

export function visualTextStyle(kind: 'text' | 'muted' | 'accent' | 'accentSoft' | 'success' | 'danger' | 'warning' = 'text') {
  const theme = ACTIVE_VISUAL_THEME;
  return {
    color:
      kind === 'muted' ? theme.muted :
      kind === 'accent' ? theme.accent :
      kind === 'accentSoft' ? theme.accent_soft :
      kind === 'success' ? theme.success :
      kind === 'danger' ? theme.danger :
      kind === 'warning' ? theme.warning :
      theme.text,
  };
}

export function visualTopBarStyle() {
  const theme = ACTIVE_VISUAL_THEME;
  return {
    backgroundColor: rgba(theme.topbar, 0.94),
    borderBottomColor: theme.border,
  };
}

export function visualRootStyle() {
  return { backgroundColor: ACTIVE_VISUAL_THEME.background };
}

export function visualImageStyle() {
  return { opacity: ACTIVE_VISUAL_THEME.image_opacity };
}

export function visualShadeStyle() {
  const theme = ACTIVE_VISUAL_THEME;
  return { backgroundColor: rgba(theme.background, theme.shade_opacity) };
}

export function VisualThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<VisualTheme>(DEFAULT_VISUAL_THEME);
  const [loading, setLoading] = useState(true);
  ACTIVE_VISUAL_THEME = theme;

  const refresh = async () => {
    try {
      const result = await fetchVisualTheme();
      if (result?.theme) setTheme({ ...DEFAULT_VISUAL_THEME, ...result.theme });
    } catch {
      // Keep the APK usable with the bundled theme if the API is unavailable.
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const save = async (next: VisualTheme) => {
    const result = await saveVisualTheme(next);
    const applied = { ...DEFAULT_VISUAL_THEME, ...result.theme };
    setTheme(applied);
    return applied;
  };

  const reset = async () => {
    const result = await resetVisualTheme();
    const applied = { ...DEFAULT_VISUAL_THEME, ...result.theme };
    setTheme(applied);
    return applied;
  };

  return (
    <ThemeContext.Provider value={{ theme, loading, refresh, save, reset }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useVisualTheme() {
  return useContext(ThemeContext);
}

const PRESETS: { name: string; patch: Partial<VisualTheme> }[] = [
  {
    name: 'AJPA',
    patch: DEFAULT_VISUAL_THEME,
  },
  {
    name: 'NEGRO',
    patch: {
      accent: '#f0f3f7',
      accent_soft: '#c7ced8',
      background: '#030303',
      panel: '#101010',
      panel_alt: '#171717',
      border: '#323232',
      text: '#ffffff',
      muted: '#9ea3aa',
      topbar: '#050505',
      panel_opacity: 0.90,
      shade_opacity: 0.36,
    },
  },
  {
    name: 'ESTADIO',
    patch: {
      accent: '#38a7ff',
      accent_soft: '#9bd5ff',
      background: '#020b13',
      panel: '#071a28',
      panel_alt: '#0b2435',
      border: '#1e516f',
      text: '#f5fbff',
      muted: '#9ab0bf',
      topbar: '#03111b',
      panel_opacity: 0.82,
      image_opacity: 0.95,
      shade_opacity: 0.18,
    },
  },
  {
    name: 'ORO',
    patch: {
      accent: '#d9b55a',
      accent_soft: '#f0d88f',
      background: '#090806',
      panel: '#17130b',
      panel_alt: '#211b0f',
      border: '#5b4b27',
      text: '#fffaf0',
      muted: '#b8ad96',
      topbar: '#0c0a05',
      warning: '#e4bd59',
      panel_opacity: 0.88,
      shade_opacity: 0.32,
    },
  },
];

function clampNumber(value: string, fallback: number, minimum: number, maximum: number) {
  const parsed = Number(value.replace(',', '.'));
  if (!Number.isFinite(parsed)) return fallback;
  return Math.max(minimum, Math.min(maximum, parsed));
}

export default function VisualThemeEditor() {
  const { theme, save, reset } = useVisualTheme();
  const [draft, setDraft] = useState<VisualTheme>(theme);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setDraft(theme);
  }, [theme]);

  const card = useMemo(() => ({
    backgroundColor: rgba(draft.panel, draft.panel_opacity),
    borderColor: draft.border,
    borderWidth: 1,
    borderRadius: draft.card_radius,
  }), [draft]);

  const set = <K extends keyof VisualTheme,>(key: K, value: VisualTheme[K]) => {
    setDraft(current => ({ ...current, [key]: value }));
  };

  const saveNow = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const applied = await save(draft);
      setDraft(applied);
      Alert.alert('Estética guardada', 'El nuevo diseño quedó activo para AJPA Mobile.');
    } catch (error) {
      const message = typeof error === 'object' && error && 'message' in error
        ? String((error as { message?: string }).message)
        : 'No se pudo guardar la estética.';
      Alert.alert('No se pudo guardar', message);
    } finally {
      setBusy(false);
    }
  };

  const resetNow = () => {
    Alert.alert(
      'Restaurar diseño',
      '¿Volver al diseño original de AJPA?',
      [
        { text: 'Cancelar', style: 'cancel' },
        {
          text: 'RESTAURAR',
          style: 'destructive',
          onPress: async () => {
            setBusy(true);
            try {
              const applied = await reset();
              setDraft(applied);
            } catch (error) {
              const message = typeof error === 'object' && error && 'message' in error
                ? String((error as { message?: string }).message)
                : 'No se pudo restaurar la estética.';
              Alert.alert('No se pudo restaurar', message);
            } finally {
              setBusy(false);
            }
          },
        },
      ],
    );
  };

  const colorField = (label: string, key: keyof Pick<VisualTheme,
    'accent' | 'accent_soft' | 'background' | 'panel' | 'panel_alt' | 'border' |
    'text' | 'muted' | 'success' | 'danger' | 'warning' | 'topbar'>) => (
      <View style={{ gap: 6 }}>
        <Text style={{ color: draft.accent_soft, fontSize: 9, fontWeight: '900', letterSpacing: 1 }}>{label}</Text>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <View style={{ width: 34, height: 34, borderRadius: 10, backgroundColor: draft[key], borderWidth: 1, borderColor: draft.border }} />
          <TextInput
            value={draft[key]}
            onChangeText={value => set(key, value.toLowerCase() as VisualTheme[typeof key])}
            autoCapitalize="none"
            maxLength={7}
            placeholder="#RRGGBB"
            placeholderTextColor={draft.muted}
            style={{
              flex: 1,
              minHeight: 42,
              borderRadius: 11,
              borderWidth: 1,
              borderColor: draft.border,
              backgroundColor: rgba(draft.background, 0.72),
              color: draft.text,
              paddingHorizontal: 12,
              fontWeight: '800',
            }}
          />
        </View>
      </View>
    );

  const numberField = (
    label: string,
    key: 'card_radius' | 'button_radius' | 'content_padding',
    min: number,
    max: number,
  ) => (
    <View style={{ flex: 1, minWidth: 130, gap: 6 }}>
      <Text style={{ color: draft.accent_soft, fontSize: 9, fontWeight: '900', letterSpacing: 1 }}>{label}</Text>
      <TextInput
        value={String(draft[key])}
        keyboardType="number-pad"
        onChangeText={value => set(key, Math.round(clampNumber(value, draft[key], min, max)))}
        style={{
          minHeight: 42,
          borderRadius: 11,
          borderWidth: 1,
          borderColor: draft.border,
          backgroundColor: rgba(draft.background, 0.72),
          color: draft.text,
          paddingHorizontal: 12,
          fontWeight: '800',
        }}
      />
    </View>
  );

  const percentField = (
    label: string,
    key: 'panel_opacity' | 'image_opacity' | 'shade_opacity',
    min: number,
    max: number,
  ) => (
    <View style={{ flex: 1, minWidth: 130, gap: 6 }}>
      <Text style={{ color: draft.accent_soft, fontSize: 9, fontWeight: '900', letterSpacing: 1 }}>{label}</Text>
      <TextInput
        value={String(Math.round(draft[key] * 100))}
        keyboardType="number-pad"
        onChangeText={value => set(key, clampNumber(value, draft[key] * 100, min * 100, max * 100) / 100)}
        style={{
          minHeight: 42,
          borderRadius: 11,
          borderWidth: 1,
          borderColor: draft.border,
          backgroundColor: rgba(draft.background, 0.72),
          color: draft.text,
          paddingHorizontal: 12,
          fontWeight: '800',
        }}
      />
    </View>
  );

  return (
    <ScrollView
      contentContainerStyle={{
        padding: draft.content_padding,
        paddingBottom: 42,
        gap: draft.compact ? 8 : 13,
      }}
      keyboardShouldPersistTaps="handled"
    >
      <View>
        <Text style={{ color: draft.accent, fontSize: 10, fontWeight: '900', letterSpacing: 1.6 }}>STAFF · EDITOR VISUAL</Text>
        <Text style={{ color: draft.text, fontSize: 27, fontWeight: '900', marginTop: 4 }}>Diseño de la app</Text>
        <Text style={{ color: draft.muted, fontSize: 12.5, lineHeight: 18, marginTop: 5 }}>
          Cambiá la identidad visual y revisala en la vista previa antes de aplicarla para todos.
        </Text>
      </View>

      <View style={[card, { padding: 14, gap: 10 }]}>
        <Text style={{ color: draft.accent_soft, fontSize: 9, fontWeight: '900', letterSpacing: 1.2 }}>VISTA PREVIA</Text>
        <View style={{
          minHeight: 82,
          borderRadius: draft.card_radius,
          borderWidth: 1,
          borderColor: draft.border,
          backgroundColor: rgba(draft.panel_alt, draft.panel_opacity),
          padding: 13,
        }}>
          <Text style={{ color: draft.text, fontSize: 16, fontWeight: '900' }}>Mercado de Pases</Text>
          <Text style={{ color: draft.muted, fontSize: 11, marginTop: 4 }}>Así se verán tarjetas, textos y acentos.</Text>
          <View style={{ flexDirection: 'row', gap: 8, marginTop: 12 }}>
            <View style={{ height: 34, borderRadius: draft.button_radius, backgroundColor: draft.accent, paddingHorizontal: 14, justifyContent: 'center' }}>
              <Text style={{ color: draft.text, fontWeight: '900', fontSize: 9 }}>BOTÓN</Text>
            </View>
            <View style={{ height: 34, borderRadius: draft.button_radius, borderWidth: 1, borderColor: draft.border, paddingHorizontal: 14, justifyContent: 'center' }}>
              <Text style={{ color: draft.accent_soft, fontWeight: '900', fontSize: 9 }}>SECUNDARIO</Text>
            </View>
          </View>
        </View>
      </View>

      <View style={[card, { padding: 14, gap: 10 }]}>
        <Text style={{ color: draft.accent_soft, fontSize: 9, fontWeight: '900', letterSpacing: 1.2 }}>PRESETS</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          {PRESETS.map(preset => (
            <Pressable
              key={preset.name}
              onPress={() => setDraft(current => ({ ...current, ...preset.patch }))}
              style={{
                minHeight: 38,
                paddingHorizontal: 14,
                borderRadius: draft.button_radius,
                alignItems: 'center',
                justifyContent: 'center',
                borderWidth: 1,
                borderColor: draft.border,
                backgroundColor: rgba(draft.panel_alt, 0.92),
              }}
            >
              <Text style={{ color: draft.text, fontSize: 9, fontWeight: '900', letterSpacing: 0.8 }}>{preset.name}</Text>
            </Pressable>
          ))}
        </View>
      </View>

      <View style={[card, { padding: 14, gap: 13 }]}>
        <Text style={{ color: draft.accent_soft, fontSize: 9, fontWeight: '900', letterSpacing: 1.2 }}>COLORES</Text>
        {colorField('COLOR PRINCIPAL', 'accent')}
        {colorField('ACENTO SUAVE', 'accent_soft')}
        {colorField('FONDO GENERAL', 'background')}
        {colorField('TARJETAS', 'panel')}
        {colorField('TARJETAS SECUNDARIAS', 'panel_alt')}
        {colorField('BORDES', 'border')}
        {colorField('TEXTO PRINCIPAL', 'text')}
        {colorField('TEXTO SECUNDARIO', 'muted')}
        {colorField('BARRA SUPERIOR', 'topbar')}
        {colorField('ÉXITO', 'success')}
        {colorField('PELIGRO', 'danger')}
        {colorField('AVISO', 'warning')}
      </View>

      <View style={[card, { padding: 14, gap: 13 }]}>
        <Text style={{ color: draft.accent_soft, fontSize: 9, fontWeight: '900', letterSpacing: 1.2 }}>FORMA Y PROFUNDIDAD</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
          {numberField('RADIO TARJETAS', 'card_radius', 4, 32)}
          {numberField('RADIO BOTONES', 'button_radius', 4, 28)}
          {numberField('ESPACIADO', 'content_padding', 8, 28)}
          {percentField('OPACIDAD TARJETAS %', 'panel_opacity', 0.35, 1)}
          {percentField('IMAGEN DE FONDO %', 'image_opacity', 0.10, 1)}
          {percentField('OSCURECIDO %', 'shade_opacity', 0, 0.80)}
        </View>
        <Pressable
          onPress={() => set('compact', !draft.compact)}
          style={{
            minHeight: 44,
            borderRadius: draft.button_radius,
            borderWidth: 1,
            borderColor: draft.border,
            backgroundColor: rgba(draft.panel_alt, 0.85),
            flexDirection: 'row',
            alignItems: 'center',
            justifyContent: 'space-between',
            paddingHorizontal: 13,
          }}
        >
          <Text style={{ color: draft.text, fontWeight: '900', fontSize: 11 }}>MODO COMPACTO</Text>
          <Text style={{ color: draft.compact ? draft.success : draft.muted, fontWeight: '900' }}>{draft.compact ? 'ACTIVO' : 'DESACTIVADO'}</Text>
        </Pressable>
      </View>

      <Pressable
        disabled={busy}
        onPress={saveNow}
        style={{
          minHeight: 50,
          borderRadius: draft.button_radius,
          backgroundColor: draft.accent,
          alignItems: 'center',
          justifyContent: 'center',
          opacity: busy ? 0.5 : 1,
        }}
      >
        {busy ? <ActivityIndicator color={draft.text} /> : <Text style={{ color: draft.text, fontWeight: '900', letterSpacing: 0.8 }}>APLICAR PARA TODOS</Text>}
      </Pressable>

      <Pressable
        disabled={busy}
        onPress={resetNow}
        style={{
          minHeight: 46,
          borderRadius: draft.button_radius,
          borderWidth: 1,
          borderColor: draft.border,
          backgroundColor: rgba(draft.panel, 0.75),
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <Text style={{ color: draft.danger, fontWeight: '900', letterSpacing: 0.7 }}>RESTAURAR DISEÑO ORIGINAL</Text>
      </Pressable>
    </ScrollView>
  );
}
