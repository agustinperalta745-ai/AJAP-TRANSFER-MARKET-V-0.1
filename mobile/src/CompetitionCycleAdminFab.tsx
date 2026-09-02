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

export default function CompetitionCycleAdminFab() {
  const [cycle, setCycle] = useState<CycleState | null>(null);
  const [visible, setVisible] = useState(false);
  const [loading, setLoading] = useState(false);
  const [authorized, setAuthorized] = useState(false);

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

  const advance = useCallback(() => {
    if (!cycle || loading) return;
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
  }, [cycle, loading, refresh]);

  if (!authorized) return null;

  return (
    <>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Gestionar etapa AJPA"
        onPress={() => {
          setVisible(true);
          void refresh(false);
        }}
        style={({ pressed }) => [styles.fab, pressed && styles.pressed]}
      >
        <Text style={styles.fabText}>🗓️ ETAPA</Text>
      </Pressable>

      <Modal visible={visible} transparent animationType="fade" onRequestClose={() => setVisible(false)}>
        <View style={styles.backdrop}>
          <View style={styles.card}>
            <View style={styles.headerRow}>
              <View style={styles.headerTextWrap}>
                <Text style={styles.eyebrow}>ADMINISTRACIÓN</Text>
                <Text style={styles.title}>Ciclo AJPA</Text>
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
                  <Text style={styles.infoTitle}>🔄 Por competencia</Text>
                  <Text style={styles.infoText}>
                    Tabla, goleadores, PJ/PG/PE/PP, GF/GC y estadísticas de la competencia activa.
                  </Text>
                </View>

                <View style={styles.nextBox}>
                  <Text style={styles.smallLabel}>SIGUIENTE PASO</Text>
                  <Text style={styles.nextTitle}>{cycle.next_action.label}</Text>
                  <Text style={styles.nextDescription}>{cycle.next_action.description}</Text>
                </View>

                <Pressable
                  disabled={loading}
                  onPress={advance}
                  style={({ pressed }) => [styles.advanceButton, (pressed || loading) && styles.pressed]}
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
                <Text style={styles.loadingText}>Cargando etapa...</Text>
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
    maxHeight: '86%',
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
