import React, { useState } from 'react';
import {
  ActivityIndicator,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { apiRequest, RosterPlayer } from './api';

type StatItem = {
  key: string;
  label: string;
  value: string | number;
};

type StatGroup = {
  title: string;
  items: StatItem[];
};

type PlayerStatsPayload = {
  player: RosterPlayer;
  has_stats: boolean;
  groups: StatGroup[];
  special_abilities: string[];
  source: string | null;
};

const money = (value: number | null | undefined) =>
  value === null || value === undefined
    ? 'Sin definir'
    : `$${Math.round(value).toLocaleString('es-AR')}`;

const errorMessage = (error: unknown) =>
  typeof error === 'object' && error && 'message' in error
    ? String((error as { message?: string }).message || 'No se pudieron cargar las estadísticas.')
    : 'No se pudieron cargar las estadísticas.';

export default function PlayerPes6StatsButton({ player }: { player: RosterPlayer }) {
  const [visible, setVisible] = useState(false);
  const [loading, setLoading] = useState(false);
  const [stats, setStats] = useState<PlayerStatsPayload | null>(null);
  const [error, setError] = useState('');

  const openStats = async () => {
    if (player.id === null || player.id === undefined) return;
    setVisible(true);
    setLoading(true);
    setError('');
    try {
      const data = await apiRequest<PlayerStatsPayload>(`/api/v1/players/${player.id}/stats`);
      setStats(data);
    } catch (err) {
      setStats(null);
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <Pressable
        disabled={player.id === null || player.id === undefined}
        onPress={() => { void openStats(); }}
        style={({ pressed }) => [styles.statsButton, pressed && styles.pressed]}
      >
        <Text style={styles.statsButtonText}>📊 VER ESTADÍSTICAS</Text>
      </Pressable>

      <Modal
        visible={visible}
        transparent
        animationType="fade"
        onRequestClose={() => setVisible(false)}
      >
        <View style={styles.backdrop}>
          <View style={styles.modalCard}>
            <View style={styles.header}>
              <View style={styles.headerCopy}>
                <Text style={styles.eyebrow}>AJPA · PES 6</Text>
                <Text style={styles.title}>{player.name}</Text>
                <Text style={styles.subtitle}>Estadísticas originales del jugador</Text>
              </View>
              <Pressable onPress={() => setVisible(false)} style={styles.closeIcon}>
                <Text style={styles.closeIconText}>×</Text>
              </Pressable>
            </View>

            {loading ? (
              <View style={styles.loadingBox}>
                <ActivityIndicator size="large" color="#2d92ff" />
                <Text style={styles.loadingText}>Cargando estadísticas PES 6…</Text>
              </View>
            ) : null}

            {!loading && error ? (
              <View style={styles.notice}>
                <Text style={styles.noticeTitle}>No se pudieron cargar</Text>
                <Text style={styles.noticeText}>{error}</Text>
                <Pressable onPress={() => { void openStats(); }} style={styles.retryButton}>
                  <Text style={styles.retryText}>REINTENTAR</Text>
                </Pressable>
              </View>
            ) : null}

            {!loading && !error && stats ? (
              <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
                <View style={styles.summaryRow}>
                  <View style={styles.ovrBox}>
                    <Text style={styles.ovrValue}>{stats.player.ovr ?? '—'}</Text>
                    <Text style={styles.ovrLabel}>OVR AJPA</Text>
                  </View>
                  <View style={styles.summaryCopy}>
                    <Text style={styles.metaStrong}>{stats.player.position || 'Sin posición'}</Text>
                    <Text style={styles.meta}>{stats.player.club}</Text>
                    <Text style={styles.meta}>ID {stats.player.code || `AJAP-${String(stats.player.id ?? '').padStart(6, '0')}`}</Text>
                    <Text style={styles.value}>Valor mínimo {money(stats.player.market_value)}</Text>
                  </View>
                </View>

                {!stats.has_stats ? (
                  <View style={styles.notice}>
                    <Text style={styles.noticeTitle}>📂 Estadísticas PES 6</Text>
                    <Text style={styles.noticeText}>
                      Este jugador todavía no tiene estadísticas de JSON/PES 6 guardadas. No se calculan ni inventan atributos desde el OVR.
                    </Text>
                  </View>
                ) : null}

                {stats.groups.map((group) => (
                  <View key={group.title} style={styles.groupCard}>
                    <Text style={styles.groupTitle}>{group.title}</Text>
                    <View style={styles.grid}>
                      {group.items.map((item) => (
                        <View key={item.key} style={styles.statRow}>
                          <Text style={styles.statLabel}>{item.label}</Text>
                          <Text style={styles.statValue}>{String(item.value)}</Text>
                        </View>
                      ))}
                    </View>
                  </View>
                ))}

                {stats.special_abilities.length ? (
                  <View style={styles.groupCard}>
                    <Text style={styles.groupTitle}>✨ Habilidades especiales</Text>
                    <View style={styles.chips}>
                      {stats.special_abilities.map((ability) => (
                        <View key={ability} style={styles.chip}>
                          <Text style={styles.chipText}>{ability}</Text>
                        </View>
                      ))}
                    </View>
                  </View>
                ) : null}

                {stats.source ? <Text style={styles.source}>Fuente: {stats.source}</Text> : null}
              </ScrollView>
            ) : null}

            <Pressable onPress={() => setVisible(false)} style={styles.backButton}>
              <Text style={styles.backButtonText}>‹ VOLVER AL JUGADOR</Text>
            </Pressable>
          </View>
        </View>
      </Modal>
    </>
  );
}

const styles = StyleSheet.create({
  statsButton: {
    marginTop: 11,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#2d92ff',
    backgroundColor: 'rgba(45,146,255,0.12)',
    paddingVertical: 10,
    paddingHorizontal: 12,
    alignItems: 'center',
  },
  statsButtonText: { color: '#9fd0ff', fontWeight: '900', fontSize: 12, letterSpacing: 0.4 },
  pressed: { opacity: 0.7 },
  backdrop: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.78)',
    padding: 14,
    justifyContent: 'center',
  },
  modalCard: {
    maxHeight: '92%',
    borderRadius: 22,
    borderWidth: 1,
    borderColor: '#28445d',
    backgroundColor: '#07111a',
    overflow: 'hidden',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    paddingHorizontal: 18,
    paddingTop: 18,
    paddingBottom: 14,
    borderBottomWidth: 1,
    borderBottomColor: '#183044',
  },
  headerCopy: { flex: 1, paddingRight: 12 },
  eyebrow: { color: '#69b5ff', fontWeight: '900', fontSize: 10, letterSpacing: 1.1 },
  title: { color: '#f7fbff', fontWeight: '900', fontSize: 22, marginTop: 3 },
  subtitle: { color: '#92a0ad', fontSize: 12, marginTop: 3 },
  closeIcon: {
    width: 36,
    height: 36,
    borderRadius: 18,
    borderWidth: 1,
    borderColor: '#294157',
    alignItems: 'center',
    justifyContent: 'center',
  },
  closeIconText: { color: '#f7fbff', fontSize: 25, lineHeight: 27 },
  loadingBox: { paddingVertical: 42, alignItems: 'center', gap: 12 },
  loadingText: { color: '#92a0ad', fontSize: 12 },
  content: { padding: 16, gap: 12 },
  summaryRow: {
    flexDirection: 'row',
    gap: 12,
    padding: 14,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: '#1f3447',
    backgroundColor: '#0a1824',
  },
  ovrBox: {
    width: 78,
    minHeight: 78,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: '#2d92ff',
    backgroundColor: 'rgba(45,146,255,0.10)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  ovrValue: { color: '#f7fbff', fontSize: 27, fontWeight: '900' },
  ovrLabel: { color: '#8ac5ff', fontSize: 9, fontWeight: '900', marginTop: 2 },
  summaryCopy: { flex: 1, justifyContent: 'center' },
  metaStrong: { color: '#f7fbff', fontWeight: '900', fontSize: 14 },
  meta: { color: '#92a0ad', fontSize: 11, marginTop: 2 },
  value: { color: '#8ac5ff', fontSize: 11, fontWeight: '800', marginTop: 5 },
  notice: {
    margin: 16,
    marginTop: 12,
    padding: 14,
    borderRadius: 15,
    borderWidth: 1,
    borderColor: '#294157',
    backgroundColor: '#0a1824',
  },
  noticeTitle: { color: '#f7fbff', fontWeight: '900', fontSize: 13 },
  noticeText: { color: '#92a0ad', fontSize: 12, lineHeight: 18, marginTop: 5 },
  retryButton: {
    alignSelf: 'flex-start',
    marginTop: 12,
    borderRadius: 10,
    backgroundColor: '#2d92ff',
    paddingVertical: 8,
    paddingHorizontal: 12,
  },
  retryText: { color: '#fff', fontWeight: '900', fontSize: 11 },
  groupCard: {
    borderRadius: 16,
    borderWidth: 1,
    borderColor: '#1f3447',
    backgroundColor: '#0a1824',
    padding: 14,
  },
  groupTitle: { color: '#f7fbff', fontSize: 14, fontWeight: '900', marginBottom: 8 },
  grid: { gap: 1 },
  statRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
    minHeight: 35,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: '#203447',
  },
  statLabel: { color: '#b5c0c9', fontSize: 12, flex: 1 },
  statValue: { color: '#f7fbff', fontSize: 14, fontWeight: '900' },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 7 },
  chip: {
    borderRadius: 999,
    borderWidth: 1,
    borderColor: '#31516c',
    backgroundColor: '#0d2131',
    paddingVertical: 6,
    paddingHorizontal: 9,
  },
  chipText: { color: '#c9e5ff', fontSize: 11, fontWeight: '700' },
  source: { color: '#6f8393', fontSize: 10, textAlign: 'center', marginVertical: 2 },
  backButton: {
    marginHorizontal: 16,
    marginBottom: 16,
    borderRadius: 13,
    backgroundColor: '#2d92ff',
    paddingVertical: 12,
    alignItems: 'center',
  },
  backButtonText: { color: '#fff', fontWeight: '900', fontSize: 12, letterSpacing: 0.3 },
});
