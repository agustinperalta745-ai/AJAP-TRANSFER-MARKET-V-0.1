import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  AppState,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import { apiRequest, getSessionToken } from './api';

type CycleAction = {
  key: string;
  label: string;
  description: string;
};

type CycleState = {
  phase: string;
  phase_label: string;
  season_number: number;
  competition_id: number | null;
  market_open: boolean;
  market_cycle_id: number | null;
  next_action: CycleAction;
  timeline: string[];
};

type GesConfig = {
  competition_id: number;
  competition_label: string;
  league_id: string;
  ges_url: string;
  results_url: string;
  scorers_url: string;
  configured: boolean;
  updated_at: string;
  history?: Array<{ competition_id: number; competition_label: string }>;
};

type GesSyncResult = {
  ok: boolean;
  league_id: string;
  competition_id?: number;
  competition_label?: string;
  standings: number;
  matches_read: number;
  matches_new: number;
  matches_updated: number;
  scorers: number;
  warnings: string[];
};

const errorMessage = (error: unknown, fallback: string) =>
  typeof error === 'object' && error && 'message' in error
    ? String((error as { message?: string }).message || fallback)
    : fallback;

export default function CompetitionCycleAdminFab() {
  const [visible, setVisible] = useState(false);
  const [authorized, setAuthorized] = useState(false);
  const [cycle, setCycle] = useState<CycleState | null>(null);
  const [gesConfig, setGesConfig] = useState<GesConfig | null>(null);
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [gesLoading, setGesLoading] = useState(false);
  const [configSaving, setConfigSaving] = useState(false);
  const [showGesConfig, setShowGesConfig] = useState(false);
  const [gesUrl, setGesUrl] = useState('');
  const [resultsUrl, setResultsUrl] = useState('');
  const [scorersUrl, setScorersUrl] = useState('');

  const loadGesConfig = useCallback(async (showError = false) => {
    if (!getSessionToken()) return;
    try {
      const data = await apiRequest<GesConfig>('/api/v1/admin/ges-config');
      setGesConfig(data);
      setGesUrl(data.ges_url || '');
      setResultsUrl(data.results_url || '');
      setScorersUrl(data.scorers_url || '');
    } catch (error) {
      if (showError) Alert.alert('AJPA', errorMessage(error, 'No se pudo cargar la configuración GES.'));
    }
  }, []);

  const refresh = useCallback(async (showError = false) => {
    if (!getSessionToken()) {
      setAuthorized(false);
      return;
    }
    setLoading(true);
    try {
      const data = await apiRequest<CycleState>('/api/v1/admin/competition-cycle');
      setCycle(data);
      setAuthorized(true);
      await loadGesConfig(false);
    } catch (error: any) {
      const status = Number(error?.status ?? 0);
      if (status === 401 || status === 403) {
        setAuthorized(false);
        setVisible(false);
      } else if (showError) {
        Alert.alert('AJPA', errorMessage(error, 'No se pudo cargar Administración.'));
      }
    } finally {
      setLoading(false);
    }
  }, [loadGesConfig]);

  useEffect(() => {
    const first = setTimeout(() => { void refresh(false); }, 1200);
    const retry = setInterval(() => { void refresh(false); }, 15000);
    const sub = AppState.addEventListener('change', state => {
      if (state === 'active') void refresh(false);
    });
    return () => {
      clearTimeout(first);
      clearInterval(retry);
      sub.remove();
    };
  }, [refresh]);

  const seasonActive = cycle?.phase === 'season';
  const canStartSeason = cycle?.next_action?.key === 'start_season' || cycle?.next_action?.key === 'market2_season';
  const canFinishSeason = cycle?.next_action?.key === 'season_market1';

  const seasonStatus = useMemo(() => seasonActive ? 'ACTIVA' : 'CERRADA', [seasonActive]);
  const gesStatus = gesConfig?.configured ? 'CONFIGURADA' : 'NO CONFIGURADA';

  const executeCycleAction = useCallback((mode: 'start' | 'finish' | 'next') => {
    if (!cycle || actionLoading || gesLoading || configSaving) return;

    const allowed = mode === 'start'
      ? ['start_season', 'market2_season']
      : mode === 'finish'
        ? ['season_market1']
        : [cycle.next_action.key];

    if (!allowed.includes(cycle.next_action.key)) {
      const message = mode === 'start'
        ? (seasonActive ? 'La temporada ya está activa.' : `Ahora mismo la etapa es ${cycle.phase_label}.`)
        : mode === 'finish'
          ? (seasonActive ? 'La temporada todavía no puede finalizarse.' : 'No hay una temporada activa para finalizar.')
          : 'La etapa cambió. Actualizá el panel.';
      Alert.alert('AJPA', message);
      return;
    }

    const title = mode === 'start' ? 'Iniciar temporada' : mode === 'finish' ? 'Finalizar temporada' : cycle.next_action.label;
    const detail = mode === 'start'
      ? `¿Iniciar la Temporada ${cycle.next_action.key === 'market2_season' ? cycle.season_number + 1 : cycle.season_number}?\n\nEl mercado conserva su estado actual.`
      : mode === 'finish'
        ? `¿Finalizar la Temporada ${cycle.season_number}?\n\nSe archivarán tabla, resultados y goleadores. El mercado NO se abrirá ni cerrará automáticamente.`
        : `${cycle.next_action.label}\n\n${cycle.next_action.description}\n\nEl mercado conserva su estado actual.`;

    Alert.alert(title, detail, [
      { text: 'Cancelar', style: 'cancel' },
      {
        text: 'Confirmar',
        style: mode === 'finish' ? 'destructive' : 'default',
        onPress: () => {
          void (async () => {
            setActionLoading(true);
            try {
              const result = await apiRequest<{ ok: boolean; cycle: CycleState }>(
                '/api/v1/admin/competition-cycle/advance',
                { method: 'POST', body: JSON.stringify({ expected_phase: cycle.phase }) },
              );
              setCycle(result.cycle);
              await loadGesConfig(false);
              Alert.alert('AJPA', `Etapa actual: ${result.cycle.phase_label}`);
            } catch (error) {
              Alert.alert('No se pudo completar', errorMessage(error, 'Intentá nuevamente.'));
              await refresh(false);
            } finally {
              setActionLoading(false);
            }
          })();
        },
      },
    ]);
  }, [cycle, actionLoading, gesLoading, configSaving, seasonActive, loadGesConfig, refresh]);

  const setMarket = useCallback((open: boolean) => {
    if (!cycle || actionLoading || gesLoading || configSaving) return;
    if (cycle.market_open === open) {
      Alert.alert('AJPA', open ? 'El mercado ya está abierto.' : 'El mercado ya está cerrado.');
      return;
    }
    Alert.alert(
      open ? 'Abrir mercado' : 'Cerrar mercado',
      open
        ? '¿Abrir el mercado de pases? Las operaciones quedarán habilitadas inmediatamente en app y bot.'
        : '¿Cerrar el mercado de pases? Las operaciones quedarán bloqueadas inmediatamente en app y bot.',
      [
        { text: 'Cancelar', style: 'cancel' },
        {
          text: open ? 'Abrir mercado' : 'Cerrar mercado',
          style: open ? 'default' : 'destructive',
          onPress: () => {
            void (async () => {
              setActionLoading(true);
              try {
                await apiRequest<{ ok: boolean; market_open: boolean }>('/api/v1/admin/market', {
                  method: 'POST',
                  body: JSON.stringify({ open }),
                });
                await refresh(false);
                Alert.alert('AJPA', open ? 'Mercado abierto.' : 'Mercado cerrado.');
              } catch (error) {
                Alert.alert('No se pudo cambiar el mercado', errorMessage(error, 'Intentá nuevamente.'));
              } finally {
                setActionLoading(false);
              }
            })();
          },
        },
      ],
    );
  }, [cycle, actionLoading, gesLoading, configSaving, refresh]);

  const saveGesConfig = useCallback(async () => {
    if (configSaving || actionLoading || gesLoading) return;
    if (!gesUrl.trim() || !resultsUrl.trim() || !scorersUrl.trim()) {
      Alert.alert('Faltan enlaces', 'Completá GES, Resultados y Goleadores.');
      return;
    }
    setConfigSaving(true);
    try {
      const data = await apiRequest<GesConfig>('/api/v1/admin/ges-config', {
        method: 'POST',
        body: JSON.stringify({
          ges_url: gesUrl.trim(),
          results_url: resultsUrl.trim(),
          scorers_url: scorersUrl.trim(),
        }),
      });
      setGesConfig(data);
      setShowGesConfig(false);
      Alert.alert('AJPA', 'Enlaces GES guardados para esta competencia.');
    } catch (error) {
      Alert.alert('No se pudieron guardar', errorMessage(error, 'Revisá los enlaces.'));
    } finally {
      setConfigSaving(false);
    }
  }, [configSaving, actionLoading, gesLoading, gesUrl, resultsUrl, scorersUrl]);

  const syncGes = useCallback(() => {
    if (gesLoading || actionLoading || configSaving) return;
    if (!gesConfig?.configured) {
      setShowGesConfig(true);
      Alert.alert('GES no configurada', 'Primero guardá los tres enlaces de la competencia actual.');
      return;
    }
    Alert.alert(
      'GES actualizada',
      'AJPA releerá tabla, resultados y goleadores y actualizará los datos dependientes de GES.',
      [
        { text: 'Cancelar', style: 'cancel' },
        {
          text: 'Sincronizar',
          onPress: () => {
            void (async () => {
              setGesLoading(true);
              try {
                const result = await apiRequest<GesSyncResult>('/api/v1/admin/ges-sync', {
                  method: 'POST',
                  body: '{}',
                });
                const warnings = result.warnings?.length ? `\n⚠️ ${result.warnings.length} observación(es)` : '\n✅ Sin observaciones';
                Alert.alert(
                  'GES sincronizada',
                  `${result.standings} equipos en tabla\n${result.matches_read} resultados leídos\n${result.scorers} goleadores${warnings}`,
                );
                await refresh(false);
              } catch (error) {
                Alert.alert('No se pudo sincronizar GES', errorMessage(error, 'No se aplicó ningún cambio.'));
              } finally {
                setGesLoading(false);
              }
            })();
          },
        },
      ],
    );
  }, [gesLoading, actionLoading, configSaving, gesConfig, refresh]);

  if (!authorized) return null;

  const blocked = actionLoading || gesLoading || configSaving;

  return (
    <>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Panel Maestro AJPA"
        onPress={() => {
          setVisible(true);
          void refresh(false);
        }}
        style={({ pressed }) => [styles.fab, pressed && styles.pressed]}
      >
        <Text style={styles.fabText}>⚙️ ADMIN</Text>
      </Pressable>

      <Modal visible={visible} transparent animationType="fade" onRequestClose={() => setVisible(false)}>
        <View style={styles.backdrop}>
          <View style={styles.card}>
            <View style={styles.headerRow}>
              <View style={styles.headerTextWrap}>
                <Text style={styles.eyebrow}>PANEL MAESTRO · STAFF</Text>
                <Text style={styles.title}>Control central AJPA</Text>
                <Text style={styles.subtitle}>Una acción modifica el estado oficial que comparten app y bot.</Text>
              </View>
              <Pressable onPress={() => setVisible(false)} hitSlop={12}>
                <Text style={styles.close}>✕</Text>
              </Pressable>
            </View>

            {loading && !cycle ? (
              <View style={styles.loadingWrap}>
                <ActivityIndicator color="#e8eef5" />
                <Text style={styles.muted}>Cargando Administración…</Text>
              </View>
            ) : cycle ? (
              <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.scrollContent}>
                <View style={styles.statusGrid}>
                  <View style={styles.statusCard}>
                    <Text style={styles.statusLabel}>TEMPORADA</Text>
                    <Text style={[styles.statusValue, seasonActive ? styles.ok : styles.off]}>{seasonStatus}</Text>
                  </View>
                  <View style={styles.statusCard}>
                    <Text style={styles.statusLabel}>MERCADO</Text>
                    <Text style={[styles.statusValue, cycle.market_open ? styles.ok : styles.off]}>{cycle.market_open ? 'ABIERTO' : 'CERRADO'}</Text>
                  </View>
                  <View style={styles.statusCard}>
                    <Text style={styles.statusLabel}>GES</Text>
                    <Text style={[styles.statusValue, gesConfig?.configured ? styles.ok : styles.warn]}>{gesStatus}</Text>
                  </View>
                </View>

                <View style={styles.currentBox}>
                  <Text style={styles.smallLabel}>ESTADO COMPETITIVO</Text>
                  <Text style={styles.currentTitle}>{cycle.phase_label}</Text>
                  <Text style={styles.muted}>Temporada {cycle.season_number} · El mercado se controla por separado.</Text>
                </View>

                <Text style={styles.sectionLabel}>TEMPORADA</Text>
                <View style={styles.twoColumns}>
                  <MasterButton
                    emoji="▶️"
                    title="INICIAR TEMPORADA"
                    subtitle={canStartSeason ? 'Activar temporada oficial' : seasonActive ? 'Ya está activa' : 'No disponible en esta etapa'}
                    disabled={!canStartSeason || blocked}
                    onPress={() => executeCycleAction('start')}
                  />
                  <MasterButton
                    emoji="🏁"
                    title="FINALIZAR TEMPORADA"
                    subtitle={canFinishSeason ? 'Archivar datos finales' : 'Sin temporada activa'}
                    danger
                    disabled={!canFinishSeason || blocked}
                    onPress={() => executeCycleAction('finish')}
                  />
                </View>

                <Text style={styles.sectionLabel}>MERCADO DE PASES</Text>
                <View style={styles.twoColumns}>
                  <MasterButton
                    emoji="🟢"
                    title="ABRIR MERCADO"
                    subtitle="Habilitar operaciones"
                    disabled={cycle.market_open || blocked}
                    onPress={() => setMarket(true)}
                  />
                  <MasterButton
                    emoji="🔴"
                    title="CERRAR MERCADO"
                    subtitle="Bloquear operaciones"
                    danger
                    disabled={!cycle.market_open || blocked}
                    onPress={() => setMarket(false)}
                  />
                </View>

                <Text style={styles.sectionLabel}>DATOS OFICIALES</Text>
                <Pressable
                  disabled={blocked}
                  onPress={syncGes}
                  style={({ pressed }) => [styles.gesButton, (pressed || blocked) && styles.pressed]}
                >
                  {gesLoading ? <ActivityIndicator color="#08111a" /> : <Text style={styles.gesButtonText}>🔄 GES ACTUALIZADA</Text>}
                  <Text style={styles.gesButtonSub}>Releer tabla, resultados, goleadores e historiales dependientes</Text>
                </Pressable>

                <Pressable onPress={() => setShowGesConfig(value => !value)} style={styles.secondaryButton}>
                  <Text style={styles.secondaryText}>{showGesConfig ? '▲ OCULTAR CONFIGURACIÓN GES' : '⚙️ CONFIGURAR ENLACES GES'}</Text>
                </Pressable>

                {showGesConfig ? (
                  <View style={styles.configBox}>
                    <Text style={styles.inputLabel}>GES / TABLA</Text>
                    <TextInput value={gesUrl} onChangeText={setGesUrl} autoCapitalize="none" autoCorrect={false} keyboardType="url" placeholder="URL de tabla GES" placeholderTextColor="#607080" style={styles.input} />
                    <Text style={styles.inputLabel}>RESULTADOS</Text>
                    <TextInput value={resultsUrl} onChangeText={setResultsUrl} autoCapitalize="none" autoCorrect={false} keyboardType="url" placeholder="URL de resultados" placeholderTextColor="#607080" style={styles.input} />
                    <Text style={styles.inputLabel}>GOLEADORES</Text>
                    <TextInput value={scorersUrl} onChangeText={setScorersUrl} autoCapitalize="none" autoCorrect={false} keyboardType="url" placeholder="URL de goleadores" placeholderTextColor="#607080" style={styles.input} />
                    <Pressable disabled={blocked} onPress={() => { void saveGesConfig(); }} style={({ pressed }) => [styles.saveButton, (pressed || blocked) && styles.pressed]}>
                      {configSaving ? <ActivityIndicator /> : <Text style={styles.saveText}>💾 GUARDAR ENLACES</Text>}
                    </Pressable>
                  </View>
                ) : null}

                <View style={styles.separator} />
                <Text style={styles.sectionLabel}>ETAPAS Y COPA</Text>
                <View style={styles.nextBox}>
                  <Text style={styles.smallLabel}>SIGUIENTE ACCIÓN COMPETITIVA</Text>
                  <Text style={styles.nextTitle}>{cycle.next_action.label}</Text>
                  <Text style={styles.muted}>{cycle.next_action.description}</Text>
                  <Pressable disabled={blocked} onPress={() => executeCycleAction('next')} style={({ pressed }) => [styles.secondaryButton, (pressed || blocked) && styles.pressed]}>
                    <Text style={styles.secondaryText}>GESTIONAR ESTA ETAPA</Text>
                  </Pressable>
                </View>

                <Text style={styles.footerNote}>Planteles, saldos, fichajes e historial de clásicos se conservan. Abrir/cerrar mercado nunca depende del cambio de etapa.</Text>
              </ScrollView>
            ) : (
              <View style={styles.loadingWrap}>
                <Text style={styles.muted}>No se pudo cargar el panel.</Text>
                <Pressable onPress={() => { void refresh(true); }} style={styles.secondaryButton}><Text style={styles.secondaryText}>REINTENTAR</Text></Pressable>
              </View>
            )}
          </View>
        </View>
      </Modal>
    </>
  );
}

function MasterButton({
  emoji,
  title,
  subtitle,
  onPress,
  disabled = false,
  danger = false,
}: {
  emoji: string;
  title: string;
  subtitle: string;
  onPress: () => void;
  disabled?: boolean;
  danger?: boolean;
}) {
  return (
    <Pressable
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [styles.masterButton, danger && styles.masterDanger, disabled && styles.disabled, pressed && !disabled && styles.pressed]}
    >
      <Text style={styles.masterEmoji}>{emoji}</Text>
      <Text style={[styles.masterTitle, danger && styles.dangerText]}>{title}</Text>
      <Text style={styles.masterSub}>{subtitle}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  fab: {
    position: 'absolute',
    right: 14,
    bottom: 76,
    zIndex: 80,
    minHeight: 46,
    minWidth: 98,
    borderRadius: 23,
    paddingHorizontal: 15,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#eef2f5',
    borderWidth: 1,
    borderColor: '#ffffff',
    shadowColor: '#000',
    shadowOpacity: 0.35,
    shadowRadius: 9,
    shadowOffset: { width: 0, height: 4 },
    elevation: 9,
  },
  fabText: { color: '#071019', fontSize: 11, fontWeight: '900', letterSpacing: 0.8 },
  backdrop: { flex: 1, justifyContent: 'center', padding: 14, backgroundColor: 'rgba(0,0,0,0.72)' },
  card: {
    maxHeight: '91%',
    borderRadius: 24,
    borderWidth: 1,
    borderColor: '#263746',
    backgroundColor: '#071019',
    overflow: 'hidden',
  },
  headerRow: { flexDirection: 'row', alignItems: 'flex-start', padding: 18, borderBottomWidth: 1, borderBottomColor: '#182734' },
  headerTextWrap: { flex: 1, paddingRight: 12 },
  eyebrow: { color: '#8cc7ff', fontSize: 10, fontWeight: '900', letterSpacing: 1.6, marginBottom: 5 },
  title: { color: '#f5f8fb', fontSize: 24, fontWeight: '900' },
  subtitle: { color: '#8fa2b2', fontSize: 12, lineHeight: 17, marginTop: 5 },
  close: { color: '#dce7ef', fontSize: 23, fontWeight: '900' },
  scrollContent: { padding: 15, paddingBottom: 24, gap: 10 },
  loadingWrap: { padding: 30, alignItems: 'center', gap: 12 },
  statusGrid: { flexDirection: 'row', gap: 7 },
  statusCard: { flex: 1, minHeight: 66, borderRadius: 14, borderWidth: 1, borderColor: '#1f3445', backgroundColor: '#0b1823', padding: 10, justifyContent: 'center' },
  statusLabel: { color: '#72889a', fontSize: 8, fontWeight: '900', letterSpacing: 1 },
  statusValue: { fontSize: 11, fontWeight: '900', marginTop: 4 },
  ok: { color: '#62df94' },
  off: { color: '#ff8a91' },
  warn: { color: '#ffc875' },
  currentBox: { borderRadius: 16, padding: 14, backgroundColor: '#0b1721', borderWidth: 1, borderColor: '#203546' },
  smallLabel: { color: '#6f879a', fontSize: 9, fontWeight: '900', letterSpacing: 1.2 },
  currentTitle: { color: '#f6f9fc', fontSize: 18, fontWeight: '900', marginTop: 4 },
  muted: { color: '#93a6b5', fontSize: 11.5, lineHeight: 17, marginTop: 4 },
  sectionLabel: { color: '#a9c1d5', fontSize: 9, fontWeight: '900', letterSpacing: 1.4, marginTop: 6 },
  twoColumns: { flexDirection: 'row', gap: 8 },
  masterButton: { flex: 1, minHeight: 112, borderRadius: 17, padding: 13, borderWidth: 1, borderColor: '#25425a', backgroundColor: '#0b1b28', justifyContent: 'center' },
  masterDanger: { borderColor: '#5d3037', backgroundColor: '#211116' },
  masterEmoji: { fontSize: 23, marginBottom: 7 },
  masterTitle: { color: '#f5f8fb', fontSize: 12, fontWeight: '900', lineHeight: 16 },
  dangerText: { color: '#ff9aa0' },
  masterSub: { color: '#8196a7', fontSize: 10, lineHeight: 14, marginTop: 4 },
  disabled: { opacity: 0.38 },
  pressed: { opacity: 0.65 },
  gesButton: { borderRadius: 16, minHeight: 64, backgroundColor: '#edf2f5', padding: 12, alignItems: 'center', justifyContent: 'center' },
  gesButtonText: { color: '#071019', fontSize: 13, fontWeight: '900' },
  gesButtonSub: { color: '#3d4f5c', fontSize: 9.5, textAlign: 'center', marginTop: 3 },
  secondaryButton: { minHeight: 44, borderRadius: 13, borderWidth: 1, borderColor: '#2a4357', backgroundColor: '#0a1620', alignItems: 'center', justifyContent: 'center', paddingHorizontal: 12, marginTop: 7 },
  secondaryText: { color: '#b8d2e6', fontSize: 10.5, fontWeight: '900', letterSpacing: 0.4 },
  configBox: { borderRadius: 16, borderWidth: 1, borderColor: '#203748', backgroundColor: '#09151e', padding: 13, gap: 7 },
  inputLabel: { color: '#8198aa', fontSize: 9, fontWeight: '900', letterSpacing: 1 },
  input: { minHeight: 44, borderRadius: 11, borderWidth: 1, borderColor: '#263c4d', backgroundColor: '#050e15', color: '#eef5fa', paddingHorizontal: 11, fontSize: 11 },
  saveButton: { minHeight: 46, borderRadius: 12, backgroundColor: '#e8eef3', alignItems: 'center', justifyContent: 'center', marginTop: 4 },
  saveText: { color: '#071019', fontSize: 11, fontWeight: '900' },
  separator: { height: 1, backgroundColor: '#1b2d3b', marginVertical: 4 },
  nextBox: { borderRadius: 15, padding: 13, borderWidth: 1, borderColor: '#223b4e', backgroundColor: '#091722' },
  nextTitle: { color: '#f2f6fa', fontSize: 13, fontWeight: '900', marginTop: 5 },
  footerNote: { color: '#6f8393', fontSize: 10, lineHeight: 15, textAlign: 'center', marginTop: 4 },
});
