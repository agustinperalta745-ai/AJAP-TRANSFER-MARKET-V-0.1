import React, { useCallback, useEffect, useState } from 'react';
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
  persistent_note: string;
  competition_note: string;
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

export default function CompetitionCycleAdminFab() {
  const [cycle, setCycle] = useState<CycleState | null>(null);
  const [visible, setVisible] = useState(false);
  const [loading, setLoading] = useState(false);
  const [gesLoading, setGesLoading] = useState(false);
  const [authorized, setAuthorized] = useState(false);
  const [gesConfig, setGesConfig] = useState<GesConfig | null>(null);
  const [gesUrl, setGesUrl] = useState('');
  const [resultsUrl, setResultsUrl] = useState('');
  const [scorersUrl, setScorersUrl] = useState('');
  const [configLoading, setConfigLoading] = useState(false);
  const [configSaving, setConfigSaving] = useState(false);

  const loadGesConfig = useCallback(async (showError = false) => {
    if (!getSessionToken()) return;
    setConfigLoading(true);
    try {
      const data = await apiRequest<GesConfig>('/api/v1/admin/ges-config');
      setGesConfig(data);
      setGesUrl(data.ges_url || '');
      setResultsUrl(data.results_url || '');
      setScorersUrl(data.scorers_url || '');
    } catch (error: any) {
      if (showError) {
        Alert.alert('AJPA', String(error?.message || 'No se pudieron cargar los enlaces GES.'));
      }
    } finally {
      setConfigLoading(false);
    }
  }, []);

  const refresh = useCallback(async (showError = false) => {
    if (!getSessionToken()) {
      setAuthorized(false);
      return;
    }
    try {
      const data = await apiRequest<CycleState>('/api/v1/admin/competition-cycle');
      setCycle(data);
      setAuthorized(true);
    } catch (error: any) {
      const status = Number(error?.status ?? 0);
      if (status === 401 || status === 403) {
        setAuthorized(false);
        setVisible(false);
        return;
      }
      if (showError) {
        Alert.alert('AJPA', String(error?.message || 'No se pudo cargar la etapa actual.'));
      }
    }
  }, []);

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

  useEffect(() => {
    if (authorized && visible) void loadGesConfig(false);
  }, [authorized, visible, cycle?.competition_id, loadGesConfig]);

  const saveGesConfig = useCallback(async () => {
    if (configSaving || gesLoading || loading) return;
    if (!gesUrl.trim() || !resultsUrl.trim() || !scorersUrl.trim()) {
      Alert.alert('Faltan enlaces', 'Completá GES, Resultados y Goleadores antes de guardar.');
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
      setGesUrl(data.ges_url || '');
      setResultsUrl(data.results_url || '');
      setScorersUrl(data.scorers_url || '');
      Alert.alert(
        'Enlaces guardados',
        `${data.competition_label}\n\nEstos enlaces quedan asociados a esta competencia y no reemplazan los de temporadas anteriores.`,
      );
    } catch (error: any) {
      Alert.alert('No se pudieron guardar', String(error?.message || 'Revisá los tres enlaces.'));
    } finally {
      setConfigSaving(false);
    }
  }, [configSaving, gesLoading, loading, gesUrl, resultsUrl, scorersUrl]);

  const advance = useCallback(() => {
    if (!cycle || loading || gesLoading || configSaving) return;
    Alert.alert(
      'Confirmar cambio de etapa',
      `${cycle.next_action.label}\n\nSe archivarán las estadísticas de la competencia que termina cuando corresponda.\n\nNO se tocan planteles, saldos, fichajes ni historial de clásicos.`,
      [
        { text: 'Cancelar', style: 'cancel' },
        {
          text: 'Confirmar',
          style: 'destructive',
          onPress: () => {
            void (async () => {
              setLoading(true);
              try {
                const result = await apiRequest<{ ok: boolean; cycle: CycleState }>(
                  '/api/v1/admin/competition-cycle/advance',
                  {
                    method: 'POST',
                    body: JSON.stringify({ expected_phase: cycle.phase }),
                  },
                );
                setCycle(result.cycle);
                setGesConfig(null);
                setGesUrl('');
                setResultsUrl('');
                setScorersUrl('');
                Alert.alert('Etapa actualizada', result.cycle.phase_label);
              } catch (error: any) {
                Alert.alert('No se pudo cambiar la etapa', String(error?.message || 'Intentá nuevamente.'));
                await refresh(false);
              } finally {
                setLoading(false);
              }
            })();
          },
        },
      ],
    );
  }, [cycle, loading, gesLoading, configSaving, refresh]);

  const syncGes = useCallback(() => {
    if (gesLoading || loading || configSaving) return;
    if (!gesConfig?.configured) {
      Alert.alert('Primero guardá los enlaces', 'Antes de sincronizar, guardá los tres enlaces GES de la competencia actual.');
      return;
    }
    Alert.alert(
      'GES actualizada',
      'Usá esta opción después de terminar de cargar GES. AJPA releerá tabla, resultados y goleadores; luego actualizará historiales y las salidas del bot de Discord.',
      [
        { text: 'Cancelar', style: 'cancel' },
        {
          text: 'Releer GES',
          onPress: () => {
            void (async () => {
              setGesLoading(true);
              try {
                const result = await apiRequest<GesSyncResult>('/api/v1/admin/ges-sync', {
                  method: 'POST',
                  body: JSON.stringify({}),
                });
                const summary = [
                  result.competition_label || gesConfig.competition_label,
                  `${result.standings} equipos en tabla`,
                  `${result.matches_read} resultados leídos`,
                  `${result.matches_new} partidos nuevos`,
                  `${result.matches_updated} resultados modificados`,
                  `${result.scorers} goleadores`,
                ].join('\n');
                const warningText = result.warnings?.length
                  ? `\n\n⚠️ Revisar (${result.warnings.length}):\n${result.warnings.slice(0, 6).join('\n')}`
                  : '\n\n✅ Sin observaciones.';
                Alert.alert('GES sincronizada', `${summary}${warningText}`);
              } catch (error: any) {
                Alert.alert('No se pudo sincronizar GES', String(error?.message || 'No se aplicó ningún cambio.'));
              } finally {
                setGesLoading(false);
              }
            })();
          },
        },
      ],
    );
  }, [gesLoading, loading, configSaving, gesConfig]);

  if (!authorized) return null;

  return (
    <>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Administración AJPA"
        onPress={() => {
          setVisible(true);
          void refresh(false);
          void loadGesConfig(false);
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
                <Text style={styles.eyebrow}>ADMINISTRACIÓN</Text>
                <Text style={styles.title}>Panel AJPA</Text>
              </View>
              <Pressable onPress={() => setVisible(false)} hitSlop={12}>
                <Text style={styles.close}>✕</Text>
              </Pressable>
            </View>

            {cycle ? (
              <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.scrollContent}>
                <View style={styles.currentCard}>
                  <Text style={styles.smallLabel}>ETAPA ACTUAL</Text>
                  <Text style={styles.current}>{cycle.phase_label}</Text>
                  <Text style={styles.marketState}>
                    Mercado: {cycle.market_open ? 'ABIERTO' : 'CERRADO'}
                  </Text>
                </View>

                <View style={styles.timeline}>
                  {cycle.timeline.map((item, index) => (
                    <React.Fragment key={`${item}-${index}`}>
                      <Text style={styles.timelineItem}>{item}</Text>
                      {index < cycle.timeline.length - 1 ? <Text style={styles.arrow}>›</Text> : null}
                    </React.Fragment>
                  ))}
                </View>

                <View style={styles.infoBox}>
                  <Text style={styles.infoTitle}>🔒 Nunca se resetea</Text>
                  <Text style={styles.infoText}>
                    Planteles, saldos, fichajes, historial de transferencias e historial de clásicos.
                  </Text>
                </View>

                <View style={styles.infoBox}>
                  <Text style={styles.infoTitle}>🗂️ Historial por competencia</Text>
                  <Text style={styles.infoText}>
                    Al finalizar una competencia se conserva su tabla, goleadores, resultados y configuración GES. Una competencia nueva no pisa la anterior.
                  </Text>
                </View>

                <View style={styles.gesBox}>
                  <Text style={styles.smallLabel}>FUENTE OFICIAL · {gesConfig?.competition_label || cycle.phase_label}</Text>
                  <Text style={styles.gesTitle}>GES de esta competencia</Text>
                  <Text style={styles.gesDescription}>
                    Guardá una vez los tres enlaces correspondientes. Después, cuando termines de actualizar GES, tocá “GES actualizada”.
                  </Text>

                  {configLoading ? (
                    <View style={styles.loadingRow}>
                      <ActivityIndicator />
                      <Text style={styles.gesDescription}>Cargando enlaces…</Text>
                    </View>
                  ) : (
                    <>
                      <Text style={styles.inputLabel}>GES / TABLA</Text>
                      <TextInput
                        value={gesUrl}
                        onChangeText={setGesUrl}
                        autoCapitalize="none"
                        autoCorrect={false}
                        keyboardType="url"
                        placeholder="https://www.gesliga.com/Clasificacion..."
                        placeholderTextColor="#5f7285"
                        style={styles.input}
                      />
                      <Text style={styles.inputLabel}>RESULTADOS</Text>
                      <TextInput
                        value={resultsUrl}
                        onChangeText={setResultsUrl}
                        autoCapitalize="none"
                        autoCorrect={false}
                        keyboardType="url"
                        placeholder="https://www.gesliga.com/CuadranteResultados..."
                        placeholderTextColor="#5f7285"
                        style={styles.input}
                      />
                      <Text style={styles.inputLabel}>GOLEADORES</Text>
                      <TextInput
                        value={scorersUrl}
                        onChangeText={setScorersUrl}
                        autoCapitalize="none"
                        autoCorrect={false}
                        keyboardType="url"
                        placeholder="https://www.gesliga.com/Estadisticas..."
                        placeholderTextColor="#5f7285"
                        style={styles.input}
                      />

                      <Pressable
                        disabled={configSaving || gesLoading || loading}
                        onPress={() => { void saveGesConfig(); }}
                        style={({ pressed }) => [styles.saveButton, (pressed || configSaving) && styles.pressed]}
                      >
                        {configSaving ? <ActivityIndicator /> : <Text style={styles.saveButtonText}>💾 GUARDAR ENLACES DE ESTA TEMPORADA</Text>}
                      </Pressable>

                      <Text style={[styles.configStatus, gesConfig?.configured && styles.configOk]}>
                        {gesConfig?.configured
                          ? `✅ Configuración guardada${gesConfig.history?.length ? ` · ${gesConfig.history.length} competencia(s) archivadas/configuradas` : ''}`
                          : '⚠️ Todavía no guardaste los enlaces de esta competencia.'}
                      </Text>
                    </>
                  )}

                  <View style={styles.separator} />
                  <Text style={styles.gesDescription}>
                    La app no cambia por mensajes de Discord: solo relee la información oficial cuando Staff ejecuta esta sincronización.
                  </Text>
                  <Pressable
                    accessibilityRole="button"
                    accessibilityLabel="GES actualizada"
                    disabled={gesLoading || loading || configSaving || !gesConfig?.configured}
                    onPress={syncGes}
                    style={({ pressed }) => [styles.gesButton, (pressed || gesLoading || loading || !gesConfig?.configured) && styles.pressed]}
                  >
                    {gesLoading ? (
                      <View style={styles.loadingRow}>
                        <ActivityIndicator />
                        <Text style={styles.gesButtonText}>RELEYENDO GES…</Text>
                      </View>
                    ) : (
                      <Text style={styles.gesButtonText}>🔄 GES ACTUALIZADA</Text>
                    )}
                  </Pressable>
                </View>

                <View style={styles.nextBox}>
                  <Text style={styles.smallLabel}>SIGUIENTE PASO</Text>
                  <Text style={styles.nextTitle}>{cycle.next_action.label}</Text>
                  <Text style={styles.nextDescription}>{cycle.next_action.description}</Text>
                </View>

                <Pressable
                  disabled={loading || gesLoading || configSaving}
                  onPress={advance}
                  style={({ pressed }) => [styles.advanceButton, (pressed || loading || gesLoading || configSaving) && styles.pressed]}
                >
                  {loading ? (
                    <ActivityIndicator />
                  ) : (
                    <Text style={styles.advanceText}>{cycle.next_action.label}</Text>
                  )}
                </Pressable>
              </ScrollView>
            ) : (
              <View style={styles.loadingWrap}>
                <ActivityIndicator />
                <Text style={styles.loadingText}>Cargando administración...</Text>
              </View>
            )}
          </View>
        </View>
      </Modal>
    </>
  );
}

const styles = StyleSheet.create({
  fab: {
    position: 'absolute',
    right: 14,
    bottom: 82,
    zIndex: 90,
    elevation: 12,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.18)',
    backgroundColor: 'rgba(9,18,28,0.96)',
    borderRadius: 999,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  fabText: { color: '#fff', fontWeight: '900', fontSize: 12, letterSpacing: 0.6 },
  pressed: { opacity: 0.68 },
  backdrop: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.76)',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 18,
  },
  card: {
    width: '100%',
    maxWidth: 520,
    maxHeight: '88%',
    borderRadius: 22,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.12)',
    backgroundColor: '#071019',
    padding: 18,
  },
  headerRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 },
  headerTextWrap: { flex: 1 },
  eyebrow: { color: '#8697a8', fontWeight: '800', fontSize: 10, letterSpacing: 1.6 },
  title: { color: '#fff', fontWeight: '900', fontSize: 25, marginTop: 2 },
  close: { color: '#cbd5df', fontSize: 22, paddingLeft: 14 },
  scrollContent: { paddingBottom: 4, gap: 12 },
  currentCard: {
    borderRadius: 16,
    padding: 15,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.1)',
    backgroundColor: 'rgba(255,255,255,0.035)',
  },
  smallLabel: { color: '#8394a5', fontSize: 10, fontWeight: '900', letterSpacing: 1.3 },
  current: { color: '#fff', fontSize: 20, fontWeight: '900', marginTop: 4 },
  marketState: { color: '#a9bac9', fontSize: 12, fontWeight: '700', marginTop: 6 },
  timeline: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 5, paddingVertical: 3 },
  timelineItem: { color: '#c5d1dc', fontSize: 11, fontWeight: '800' },
  arrow: { color: '#62788c', fontSize: 18 },
  infoBox: { borderRadius: 14, padding: 13, backgroundColor: 'rgba(255,255,255,0.025)' },
  infoTitle: { color: '#fff', fontWeight: '900', fontSize: 13, marginBottom: 5 },
  infoText: { color: '#a9bac9', lineHeight: 18, fontSize: 12 },
  gesBox: {
    borderRadius: 16,
    padding: 15,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.14)',
    backgroundColor: 'rgba(255,255,255,0.045)',
    gap: 7,
  },
  gesTitle: { color: '#fff', fontSize: 18, fontWeight: '900' },
  gesDescription: { color: '#afbfcd', fontSize: 12, lineHeight: 18 },
  inputLabel: { color: '#93a6b7', fontSize: 10, fontWeight: '900', letterSpacing: 0.8, marginTop: 3 },
  input: {
    minHeight: 44,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.12)',
    backgroundColor: 'rgba(0,0,0,0.26)',
    color: '#fff',
    fontSize: 12,
    paddingHorizontal: 12,
    paddingVertical: 9,
  },
  saveButton: {
    minHeight: 46,
    borderRadius: 13,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 12,
    marginTop: 5,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.18)',
    backgroundColor: 'rgba(255,255,255,0.08)',
  },
  saveButtonText: { color: '#fff', fontSize: 11, fontWeight: '900', textAlign: 'center' },
  configStatus: { color: '#ffc16f', fontSize: 11, lineHeight: 16, fontWeight: '700' },
  configOk: { color: '#82dda3' },
  separator: { height: 1, backgroundColor: 'rgba(255,255,255,0.09)', marginVertical: 5 },
  gesButton: {
    minHeight: 48,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 14,
    marginTop: 4,
    backgroundColor: '#f2f5f7',
  },
  gesButtonText: { color: '#071019', fontSize: 12, fontWeight: '900', textAlign: 'center' },
  loadingRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8 },
  nextBox: {
    borderRadius: 16,
    padding: 15,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.12)',
    backgroundColor: 'rgba(255,255,255,0.05)',
  },
  nextTitle: { color: '#fff', fontSize: 15, fontWeight: '900', marginTop: 5 },
  nextDescription: { color: '#afbfcd', fontSize: 12, lineHeight: 18, marginTop: 6 },
  advanceButton: {
    minHeight: 50,
    borderRadius: 15,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 14,
    backgroundColor: '#f2f5f7',
  },
  advanceText: { color: '#071019', fontSize: 12, fontWeight: '900', textAlign: 'center' },
  loadingWrap: { minHeight: 180, alignItems: 'center', justifyContent: 'center', gap: 10 },
  loadingText: { color: '#a9bac9', fontWeight: '700' },
});
