import React, { useCallback, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { apiRequest } from './api';

type Standing = {
  team: string;
  pj: number;
  pg: number;
  pe: number;
  pp: number;
  gf: number;
  gc: number;
  dg?: number;
  pts: number;
};

type Scorer = { player: string; team: string; goals: number };
type Match = {
  id: number | string;
  home_team: string;
  away_team: string;
  home_goals: number;
  away_goals: number;
};

type Competition = {
  id: number;
  kind: string;
  season_number: number;
  label: string;
  status: string;
  standings: Standing[];
  scorers: Scorer[];
  matches: Match[];
};

type HistoryPayload = { competitions: Competition[] };
type Section = 'tabla' | 'goleadores' | 'resultados';

export default function SeasonHistoryFab() {
  const [visible, setVisible] = useState(false);
  const [loading, setLoading] = useState(false);
  const [competitions, setCompetitions] = useState<Competition[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [section, setSection] = useState<Section>('tabla');

  const selected = useMemo(
    () => competitions.find(item => item.id === selectedId) || competitions[0] || null,
    [competitions, selectedId],
  );

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiRequest<HistoryPayload>('/api/v1/league/seasons');
      const rows = Array.isArray(data.competitions) ? data.competitions : [];
      setCompetitions(rows);
      setSelectedId(current => current && rows.some(item => item.id === current) ? current : (rows[0]?.id ?? null));
    } catch (error: any) {
      Alert.alert('Historial AJPA', String(error?.message || 'No se pudieron cargar las temporadas.'));
    } finally {
      setLoading(false);
    }
  }, []);

  const open = () => {
    setVisible(true);
    void load();
  };

  return (
    <>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Temporadas anteriores"
        onPress={open}
        style={({ pressed }) => [styles.fab, pressed && styles.pressed]}
      >
        <Text style={styles.fabText}>🗂 TEMPORADAS</Text>
      </Pressable>

      <Modal visible={visible} transparent animationType="fade" onRequestClose={() => setVisible(false)}>
        <View style={styles.backdrop}>
          <View style={styles.card}>
            <View style={styles.header}>
              <View style={styles.flex}>
                <Text style={styles.eyebrow}>ARCHIVO AJPA</Text>
                <Text style={styles.title}>Temporadas y copas</Text>
                <Text style={styles.subtitle}>Cada competencia queda guardada y se puede volver a consultar.</Text>
              </View>
              <Pressable onPress={() => setVisible(false)} hitSlop={12}>
                <Text style={styles.close}>✕</Text>
              </Pressable>
            </View>

            {loading && !competitions.length ? (
              <View style={styles.loading}>
                <ActivityIndicator />
                <Text style={styles.muted}>Cargando historial…</Text>
              </View>
            ) : !competitions.length ? (
              <View style={styles.loading}>
                <Text style={styles.muted}>Todavía no hay competencias archivadas.</Text>
              </View>
            ) : (
              <>
                <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.seasonRow}>
                  {competitions.map(item => {
                    const active = item.id === selected?.id;
                    return (
                      <Pressable
                        key={item.id}
                        onPress={() => { setSelectedId(item.id); setSection('tabla'); }}
                        style={[styles.seasonChip, active && styles.seasonChipActive]}
                      >
                        <Text style={[styles.seasonChipText, active && styles.seasonChipTextActive]}>{item.label}</Text>
                        <Text style={styles.seasonStatus}>{item.status === 'active' ? 'ACTUAL' : 'FINALIZADA'}</Text>
                      </Pressable>
                    );
                  })}
                </ScrollView>

                {selected ? (
                  <>
                    <View style={styles.sectionRow}>
                      {([
                        ['tabla', 'TABLA'],
                        ['goleadores', 'GOLEADORES'],
                        ['resultados', 'RESULTADOS'],
                      ] as Array<[Section, string]>).map(([key, label]) => (
                        <Pressable
                          key={key}
                          onPress={() => setSection(key)}
                          style={[styles.sectionButton, section === key && styles.sectionButtonActive]}
                        >
                          <Text style={[styles.sectionText, section === key && styles.sectionTextActive]}>{label}</Text>
                        </Pressable>
                      ))}
                    </View>

                    <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.content}>
                      <Text style={styles.competitionTitle}>{selected.label}</Text>

                      {section === 'tabla' ? (
                        selected.standings.length ? selected.standings.map((row, index) => (
                          <View key={`${row.team}-${index}`} style={styles.tableRow}>
                            <Text style={styles.position}>{index + 1}</Text>
                            <View style={styles.flex}>
                              <Text style={styles.team}>{row.team}</Text>
                              <Text style={styles.detail}>PJ {row.pj} · {row.pg}-{row.pe}-{row.pp} · GF {row.gf} GC {row.gc}</Text>
                            </View>
                            <Text style={styles.points}>{row.pts} pts</Text>
                          </View>
                        )) : <Text style={styles.empty}>Sin datos de tabla guardados.</Text>
                      ) : null}

                      {section === 'goleadores' ? (
                        selected.scorers.length ? selected.scorers.map((row, index) => (
                          <View key={`${row.player}-${row.team}-${index}`} style={styles.tableRow}>
                            <Text style={styles.position}>{index + 1}</Text>
                            <View style={styles.flex}>
                              <Text style={styles.team}>{row.player}</Text>
                              <Text style={styles.detail}>{row.team || 'Sin equipo'}</Text>
                            </View>
                            <Text style={styles.points}>⚽ {row.goals}</Text>
                          </View>
                        )) : <Text style={styles.empty}>Sin goleadores guardados.</Text>
                      ) : null}

                      {section === 'resultados' ? (
                        selected.matches.length ? selected.matches.map(match => (
                          <View key={String(match.id)} style={styles.matchCard}>
                            <Text style={styles.matchTeam}>{match.home_team}</Text>
                            <Text style={styles.score}>{match.home_goals} - {match.away_goals}</Text>
                            <Text style={styles.matchTeam}>{match.away_team}</Text>
                          </View>
                        )) : <Text style={styles.empty}>Sin resultados guardados.</Text>
                      ) : null}
                    </ScrollView>
                  </>
                ) : null}
              </>
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
    left: 14,
    bottom: 82,
    zIndex: 88,
    elevation: 11,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.16)',
    backgroundColor: 'rgba(9,18,28,0.96)',
    borderRadius: 999,
    paddingHorizontal: 13,
    paddingVertical: 10,
  },
  fabText: { color: '#fff', fontWeight: '900', fontSize: 11, letterSpacing: 0.45 },
  pressed: { opacity: 0.68 },
  backdrop: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.78)',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 16,
  },
  card: {
    width: '100%',
    maxWidth: 560,
    height: '84%',
    borderRadius: 22,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.12)',
    backgroundColor: '#071019',
    padding: 16,
  },
  header: { flexDirection: 'row', alignItems: 'flex-start', marginBottom: 12 },
  flex: { flex: 1 },
  eyebrow: { color: '#8295a6', fontSize: 10, fontWeight: '900', letterSpacing: 1.4 },
  title: { color: '#fff', fontSize: 23, fontWeight: '900', marginTop: 2 },
  subtitle: { color: '#9badbc', fontSize: 12, lineHeight: 17, marginTop: 4 },
  close: { color: '#d1dbe4', fontSize: 22, paddingLeft: 12 },
  loading: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 10 },
  muted: { color: '#9badbc', fontWeight: '700' },
  seasonRow: { gap: 8, paddingBottom: 11 },
  seasonChip: {
    minWidth: 118,
    borderRadius: 13,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.1)',
    backgroundColor: 'rgba(255,255,255,0.035)',
    paddingHorizontal: 11,
    paddingVertical: 9,
  },
  seasonChipActive: { backgroundColor: '#eef3f6', borderColor: '#eef3f6' },
  seasonChipText: { color: '#d1dce5', fontSize: 12, fontWeight: '900' },
  seasonChipTextActive: { color: '#071019' },
  seasonStatus: { color: '#7f93a5', fontSize: 8, fontWeight: '900', marginTop: 3, letterSpacing: 0.7 },
  sectionRow: { flexDirection: 'row', gap: 7, marginBottom: 10 },
  sectionButton: {
    flex: 1,
    minHeight: 38,
    borderRadius: 11,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.1)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  sectionButtonActive: { backgroundColor: 'rgba(255,255,255,0.12)' },
  sectionText: { color: '#7f93a5', fontSize: 9, fontWeight: '900' },
  sectionTextActive: { color: '#fff' },
  content: { paddingBottom: 12, gap: 7 },
  competitionTitle: { color: '#fff', fontSize: 18, fontWeight: '900', marginBottom: 4 },
  tableRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 9,
    borderRadius: 12,
    padding: 10,
    backgroundColor: 'rgba(255,255,255,0.035)',
  },
  position: { color: '#7890a4', width: 22, textAlign: 'center', fontWeight: '900' },
  team: { color: '#fff', fontSize: 12, fontWeight: '900' },
  detail: { color: '#8fa2b3', fontSize: 10, marginTop: 2 },
  points: { color: '#fff', fontSize: 12, fontWeight: '900' },
  matchCard: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
    borderRadius: 12,
    padding: 12,
    backgroundColor: 'rgba(255,255,255,0.035)',
  },
  matchTeam: { color: '#eaf0f4', fontSize: 11, fontWeight: '800', flex: 1 },
  score: { color: '#fff', fontSize: 16, fontWeight: '900', minWidth: 54, textAlign: 'center' },
  empty: { color: '#8fa2b3', textAlign: 'center', paddingVertical: 24 },
});
