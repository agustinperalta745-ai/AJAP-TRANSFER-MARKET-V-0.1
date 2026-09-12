import React, { useCallback, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import { apiRequest, fetchMe, getSessionToken } from './api';

type CompetitionKey = 'champions' | 'europa';
type SeedSlot = { slot_index: number; team: string | null; source: string | null };
type CupMatch = {
  id: number;
  competition: CompetitionKey;
  round_key: string;
  round_order: number;
  match_index: number;
  home_team: string | null;
  away_team: string | null;
  home_goals: number | null;
  away_goals: number | null;
  home_penalties: number | null;
  away_penalties: number | null;
  winner_team: string | null;
  loser_team: string | null;
  status: string;
  source_home: string | null;
  source_away: string | null;
};
type CupRound = { key: string; label: string; order: number; matches: CupMatch[] };
type CupEdition = {
  id: number;
  season_number: number;
  status: 'DRAFT' | 'ACTIVE' | 'FINISHED' | string;
  champions_name: string;
  europa_name: string;
  champions_champion: string | null;
  europa_champion: string | null;
  started_at: string | null;
  finished_at: string | null;
  seed_slots: Record<CompetitionKey, SeedSlot[]>;
  rounds: Record<CompetitionKey, CupRound[]>;
};
type CupsPayload = {
  rules: {
    season_number: number;
    champions_name: string;
    europa_name: string;
    champions_qualification: string;
    europa_qualification: string;
    drop_rule: string;
    next_season_rule: string;
  };
  clubs: string[];
  qualification_suggestion: {
    champions: string[];
    europa: string[];
    europa_holder: string | null;
    warnings: string[];
  };
  edition: CupEdition | null;
};

const errorText = (error: unknown) =>
  typeof error === 'object' && error && 'message' in error
    ? String((error as { message?: string }).message || 'No se pudo completar la operación.')
    : 'No se pudo completar la operación.';

const compName = (key: CompetitionKey) => key === 'champions' ? 'Champions League' : 'Europa League';

export default function CupCenterFab() {
  const [visible, setVisible] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [isStaff, setIsStaff] = useState(false);
  const [data, setData] = useState<CupsPayload | null>(null);
  const [competition, setCompetition] = useState<CompetitionKey>('champions');
  const [slotTarget, setSlotTarget] = useState<{ competition: CompetitionKey; slot_index: number } | null>(null);
  const [editingMatch, setEditingMatch] = useState<CupMatch | null>(null);
  const [homeGoals, setHomeGoals] = useState('');
  const [awayGoals, setAwayGoals] = useState('');
  const [homePens, setHomePens] = useState('');
  const [awayPens, setAwayPens] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const payload = await apiRequest<CupsPayload>('/api/v1/cups');
      setData(payload);
      if (getSessionToken()) {
        try {
          const me = await fetchMe();
          setIsStaff(Boolean(me.is_staff));
        } catch {
          setIsStaff(false);
        }
      } else {
        setIsStaff(false);
      }
    } catch (error) {
      Alert.alert('Copas AJPA', errorText(error));
    } finally {
      setLoading(false);
    }
  }, []);

  const open = () => {
    setVisible(true);
    void load();
  };

  const mutate = async (path: string, body: Record<string, unknown>, success?: string) => {
    if (saving) return;
    setSaving(true);
    try {
      await apiRequest(path, { method: 'POST', body: JSON.stringify(body) });
      if (success) Alert.alert('Copas AJPA', success);
      await load();
    } catch (error) {
      Alert.alert('Copas AJPA', errorText(error));
    } finally {
      setSaving(false);
    }
  };

  const edition = data?.edition ?? null;
  const currentSeason = data?.rules.season_number ?? 1;
  const currentEditionReady = Boolean(edition && edition.season_number === currentSeason);
  const activeRounds = useMemo(() => edition?.rounds?.[competition] ?? [], [edition, competition]);

  const prepareEdition = () => mutate('/api/v1/cups/edition', { season_number: currentSeason }, `Copas de la Temporada ${currentSeason} preparadas.`);
  const seedFromTable = () => {
    if (!edition) return;
    Alert.alert(
      'Cargar clasificados',
      'Se cargarán los cupos según la tabla y la regla vigente. Después podés cambiar cualquier equipo manualmente antes de iniciar.',
      [
        { text: 'Cancelar', style: 'cancel' },
        { text: 'CARGAR', onPress: () => { void mutate(`/api/v1/cups/${edition.id}/seed-from-table`, {}); } },
      ],
    );
  };
  const startCups = () => {
    if (!edition) return;
    Alert.alert(
      'Iniciar Champions y Europa',
      'Al iniciar se congela la preclasificación. Los resultados harán avanzar automáticamente a los ganadores y los 8 perdedores de la primera ronda de Champions bajarán a Europa.',
      [
        { text: 'Volver', style: 'cancel' },
        { text: 'INICIAR COPAS', onPress: () => { void mutate(`/api/v1/cups/${edition.id}/start`, {}, 'Los cuadros quedaron iniciados.'); } },
      ],
    );
  };

  const chooseTeam = (team: string | null) => {
    if (!edition || !slotTarget) return;
    const target = slotTarget;
    setSlotTarget(null);
    void mutate(`/api/v1/cups/${edition.id}/slots`, {
      competition: target.competition,
      slot_index: target.slot_index,
      team,
    });
  };

  const openResult = (match: CupMatch) => {
    setEditingMatch(match);
    setHomeGoals(match.home_goals === null ? '' : String(match.home_goals));
    setAwayGoals(match.away_goals === null ? '' : String(match.away_goals));
    setHomePens(match.home_penalties === null ? '' : String(match.home_penalties));
    setAwayPens(match.away_penalties === null ? '' : String(match.away_penalties));
  };

  const saveResult = () => {
    if (!editingMatch) return;
    void mutate(`/api/v1/cups/matches/${editingMatch.id}/result`, {
      home_goals: homeGoals.trim(),
      away_goals: awayGoals.trim(),
      home_penalties: homePens.trim() || null,
      away_penalties: awayPens.trim() || null,
    }, 'Resultado guardado y cuadro actualizado.').then(() => setEditingMatch(null));
  };

  const clearResult = () => {
    if (!editingMatch) return;
    const matchId = editingMatch.id;
    Alert.alert(
      'Borrar resultado',
      'Se quitará este resultado y también su avance automático. Solo se permite si el cruce siguiente todavía no fue jugado.',
      [
        { text: 'Cancelar', style: 'cancel' },
        {
          text: 'BORRAR',
          style: 'destructive',
          onPress: () => {
            setEditingMatch(null);
            void mutate(`/api/v1/cups/matches/${matchId}/result`, { clear: true }, 'Resultado eliminado.');
          },
        },
      ],
    );
  };

  const scoreText = (match: CupMatch) => {
    if (match.home_goals === null || match.away_goals === null) return 'VS';
    return `${match.home_goals} - ${match.away_goals}`;
  };

  const renderSeedList = (key: CompetitionKey) => {
    const slots = edition?.seed_slots?.[key] ?? [];
    const expected = key === 'champions' ? 16 : 8;
    const rows = slots.length ? slots : Array.from({ length: expected }, (_, slot_index) => ({ slot_index, team: null, source: null }));
    return (
      <View style={styles.seedSection}>
        <Text style={styles.seedTitle}>{key === 'champions' ? '🏆 CHAMPIONS LEAGUE · 16 CUPOS' : '🟠 EUROPA LEAGUE · 8 CUPOS EN ESPERA'}</Text>
        <Text style={styles.seedHint}>
          {key === 'champions'
            ? 'Cada dos posiciones forman un cruce de primera ronda.'
            : 'Cada preclasificado espera al perdedor del partido equivalente de Champions.'}
        </Text>
        {rows.map((slot) => (
          <Pressable
            key={`${key}-${slot.slot_index}`}
            disabled={!isStaff || edition?.status !== 'DRAFT'}
            onPress={() => setSlotTarget({ competition: key, slot_index: slot.slot_index })}
            style={({ pressed }) => [styles.seedRow, pressed && styles.pressed]}
          >
            <Text style={styles.seedNumber}>{slot.slot_index + 1}</Text>
            <View style={styles.flex}>
              <Text style={[styles.seedTeam, !slot.team && styles.placeholder]}>{slot.team || 'Elegir equipo'}</Text>
              {slot.source ? <Text style={styles.seedSource}>{slot.source}</Text> : null}
            </View>
            {isStaff && edition?.status === 'DRAFT' ? <Text style={styles.chevron}>›</Text> : null}
          </Pressable>
        ))}
      </View>
    );
  };

  const renderMatch = (match: CupMatch) => {
    const ready = Boolean(match.home_team && match.away_team);
    const finished = match.status === 'FINISHED';
    return (
      <View key={match.id} style={[styles.matchCard, finished && styles.matchFinished]}>
        <Text style={styles.matchIndex}>PARTIDO {match.match_index + 1}</Text>
        <View style={styles.teamLine}>
          <Text style={[styles.matchTeam, match.winner_team === match.home_team && styles.winner]} numberOfLines={1}>
            {match.home_team || 'Por definir'}
          </Text>
          <Text style={styles.teamScore}>{match.home_goals ?? '—'}</Text>
        </View>
        <View style={styles.teamLine}>
          <Text style={[styles.matchTeam, match.winner_team === match.away_team && styles.winner]} numberOfLines={1}>
            {match.away_team || match.source_away || 'Por definir'}
          </Text>
          <Text style={styles.teamScore}>{match.away_goals ?? '—'}</Text>
        </View>
        {match.home_penalties !== null && match.away_penalties !== null ? (
          <Text style={styles.penaltyText}>Penales: {match.home_penalties} - {match.away_penalties}</Text>
        ) : null}
        {finished && match.winner_team ? <Text style={styles.advanceText}>✓ Avanza {match.winner_team}</Text> : null}
        {competition === 'champions' && match.round_key === 'R16' && finished && match.loser_team ? (
          <Text style={styles.dropText}>↓ {match.loser_team} pasa a Europa League</Text>
        ) : null}
        {isStaff && ready ? (
          <Pressable onPress={() => openResult(match)} style={({ pressed }) => [styles.resultButton, pressed && styles.pressed]}>
            <Text style={styles.resultButtonText}>{finished ? '✎ EDITAR RESULTADO' : '＋ CARGAR RESULTADO'}</Text>
          </Pressable>
        ) : null}
      </View>
    );
  };

  return (
    <>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Champions y Europa League"
        onPress={open}
        style={({ pressed }) => [styles.fab, pressed && styles.pressed]}
      >
        <Text style={styles.fabText}>🏆 COPAS</Text>
      </Pressable>

      <Modal visible={visible} transparent animationType="fade" onRequestClose={() => setVisible(false)}>
        <View style={styles.backdrop}>
          <View style={styles.panel}>
            <View style={styles.header}>
              <View style={styles.flex}>
                <Text style={styles.eyebrow}>AJPA · COMPETICIONES</Text>
                <Text style={styles.title}>Champions & Europa League</Text>
                <Text style={styles.subtitle}>Clasificación, descenso entre copas, cuadros y resultados oficiales.</Text>
              </View>
              <Pressable onPress={() => setVisible(false)} hitSlop={12}><Text style={styles.close}>✕</Text></Pressable>
            </View>

            {loading && !data ? (
              <View style={styles.loading}><ActivityIndicator size="large" /><Text style={styles.muted}>Cargando copas…</Text></View>
            ) : data ? (
              <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.content}>
                <View style={styles.ruleCard}>
                  <Text style={styles.ruleSeason}>TEMPORADA {data.rules.season_number}</Text>
                  <Text style={styles.ruleText}><Text style={styles.bold}>Champions:</Text> {data.rules.champions_qualification}</Text>
                  <Text style={styles.ruleText}><Text style={styles.bold}>Europa:</Text> {data.rules.europa_qualification}</Text>
                  <Text style={styles.dropRule}>{data.rules.drop_rule}</Text>
                  <Text style={styles.nextRule}>{data.rules.next_season_rule}</Text>
                </View>

                {isStaff && !currentEditionReady ? (
                  <Pressable disabled={saving} onPress={() => { void prepareEdition(); }} style={[styles.primary, saving && styles.disabled]}>
                    <Text style={styles.primaryText}>⚙️ PREPARAR COPAS · TEMPORADA {currentSeason}</Text>
                  </Pressable>
                ) : null}

                {!edition ? (
                  <View style={styles.emptyCard}>
                    <Text style={styles.emptyTitle}>Todavía no hay cuadro cargado</Text>
                    <Text style={styles.muted}>Cuando Staff prepare los preclasificados, van a aparecer acá.</Text>
                  </View>
                ) : null}

                {edition?.status === 'DRAFT' && currentEditionReady ? (
                  <>
                    <View style={styles.statusCard}>
                      <Text style={styles.statusTitle}>🧩 PRECLASIFICACIÓN</Text>
                      <Text style={styles.muted}>Staff está armando los cupos antes del inicio de las copas.</Text>
                      {data.qualification_suggestion.warnings.map((warning, index) => (
                        <Text key={`${warning}-${index}`} style={styles.warning}>⚠ {warning}</Text>
                      ))}
                    </View>
                    {isStaff ? (
                      <View style={styles.adminRow}>
                        <Pressable disabled={saving} onPress={seedFromTable} style={[styles.secondary, saving && styles.disabled]}>
                          <Text style={styles.secondaryText}>📊 CARGAR SEGÚN TABLA</Text>
                        </Pressable>
                        <Pressable disabled={saving} onPress={startCups} style={[styles.primarySmall, saving && styles.disabled]}>
                          <Text style={styles.primaryText}>▶ INICIAR COPAS</Text>
                        </Pressable>
                      </View>
                    ) : null}
                    {renderSeedList('champions')}
                    {renderSeedList('europa')}
                  </>
                ) : null}

                {edition && edition.status !== 'DRAFT' ? (
                  <>
                    <View style={styles.competitionTabs}>
                      {(['champions', 'europa'] as CompetitionKey[]).map((key) => (
                        <Pressable key={key} onPress={() => setCompetition(key)} style={[styles.tab, competition === key && styles.tabActive]}>
                          <Text style={[styles.tabText, competition === key && styles.tabTextActive]}>{key === 'champions' ? '🏆 CHAMPIONS' : '🟠 EUROPA'}</Text>
                        </Pressable>
                      ))}
                    </View>

                    {(competition === 'champions' ? edition.champions_champion : edition.europa_champion) ? (
                      <View style={styles.championCard}>
                        <Text style={styles.championEyebrow}>CAMPEÓN</Text>
                        <Text style={styles.championTeam}>{competition === 'champions' ? edition.champions_champion : edition.europa_champion}</Text>
                      </View>
                    ) : null}

                    <Text style={styles.bracketHint}>Deslizá hacia los costados para recorrer el cuadro.</Text>
                    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.bracket}>
                      {activeRounds.map((round) => (
                        <View key={`${competition}-${round.key}`} style={styles.roundColumn}>
                          <Text style={styles.roundTitle}>{round.label.toUpperCase()}</Text>
                          <Text style={styles.roundSub}>{compName(competition)}</Text>
                          <View style={styles.roundMatches}>{round.matches.map(renderMatch)}</View>
                        </View>
                      ))}
                    </ScrollView>
                  </>
                ) : null}
              </ScrollView>
            ) : null}
          </View>
        </View>
      </Modal>

      <Modal visible={Boolean(slotTarget)} transparent animationType="fade" onRequestClose={() => setSlotTarget(null)}>
        <View style={styles.backdrop}>
          <View style={styles.pickerCard}>
            <View style={styles.header}>
              <View style={styles.flex}>
                <Text style={styles.eyebrow}>STAFF · PRECLASIFICACIÓN</Text>
                <Text style={styles.modalTitle}>Elegir equipo</Text>
                <Text style={styles.subtitle}>{slotTarget ? `${compName(slotTarget.competition)} · Cupo ${slotTarget.slot_index + 1}` : ''}</Text>
              </View>
              <Pressable onPress={() => setSlotTarget(null)}><Text style={styles.close}>✕</Text></Pressable>
            </View>
            <ScrollView contentContainerStyle={styles.pickerContent}>
              <Pressable onPress={() => chooseTeam(null)} style={styles.clubOption}><Text style={styles.removeText}>— DEJAR VACÍO —</Text></Pressable>
              {(data?.clubs ?? []).map((club) => (
                <Pressable key={club} onPress={() => chooseTeam(club)} style={({ pressed }) => [styles.clubOption, pressed && styles.pressed]}>
                  <Text style={styles.clubOptionText}>{club}</Text>
                </Pressable>
              ))}
            </ScrollView>
          </View>
        </View>
      </Modal>

      <Modal visible={Boolean(editingMatch)} transparent animationType="fade" onRequestClose={() => setEditingMatch(null)}>
        <View style={styles.backdrop}>
          <View style={styles.resultModal}>
            <View style={styles.header}>
              <View style={styles.flex}>
                <Text style={styles.eyebrow}>STAFF · RESULTADO OFICIAL</Text>
                <Text style={styles.modalTitle}>{editingMatch?.home_team} vs {editingMatch?.away_team}</Text>
                <Text style={styles.subtitle}>Si empatan, cargá también la tanda de penales.</Text>
              </View>
              <Pressable onPress={() => setEditingMatch(null)}><Text style={styles.close}>✕</Text></Pressable>
            </View>

            <Text style={styles.formLabel}>RESULTADO</Text>
            <View style={styles.scoreInputs}>
              <View style={styles.scoreField}><Text style={styles.inputTeam}>{editingMatch?.home_team}</Text><TextInput value={homeGoals} onChangeText={setHomeGoals} keyboardType="number-pad" style={styles.scoreInput} placeholder="0" placeholderTextColor="#586a79" /></View>
              <Text style={styles.dash}>—</Text>
              <View style={styles.scoreField}><Text style={styles.inputTeam}>{editingMatch?.away_team}</Text><TextInput value={awayGoals} onChangeText={setAwayGoals} keyboardType="number-pad" style={styles.scoreInput} placeholder="0" placeholderTextColor="#586a79" /></View>
            </View>

            <Text style={styles.formLabel}>PENALES · SOLO SI EMPATAN</Text>
            <View style={styles.scoreInputs}>
              <TextInput value={homePens} onChangeText={setHomePens} keyboardType="number-pad" style={styles.penInput} placeholder="Local" placeholderTextColor="#586a79" />
              <Text style={styles.dash}>—</Text>
              <TextInput value={awayPens} onChangeText={setAwayPens} keyboardType="number-pad" style={styles.penInput} placeholder="Visitante" placeholderTextColor="#586a79" />
            </View>

            <Pressable disabled={saving} onPress={saveResult} style={[styles.primary, saving && styles.disabled]}>
              <Text style={styles.primaryText}>{saving ? 'GUARDANDO…' : '💾 GUARDAR RESULTADO'}</Text>
            </Pressable>
            {editingMatch?.status === 'FINISHED' ? (
              <Pressable disabled={saving} onPress={clearResult} style={styles.dangerButton}><Text style={styles.dangerText}>BORRAR RESULTADO</Text></Pressable>
            ) : null}
          </View>
        </View>
      </Modal>
    </>
  );
}

const styles = StyleSheet.create({
  fab: { position: 'absolute', left: 14, bottom: 132, zIndex: 89, elevation: 12, borderWidth: 1, borderColor: 'rgba(255,215,100,0.35)', backgroundColor: 'rgba(16,20,26,0.97)', borderRadius: 999, paddingHorizontal: 14, paddingVertical: 10 },
  fabText: { color: '#fff4cb', fontWeight: '900', fontSize: 11, letterSpacing: 0.5 },
  backdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.8)', alignItems: 'center', justifyContent: 'center', padding: 14 },
  panel: { width: '100%', maxWidth: 680, height: '90%', borderRadius: 23, borderWidth: 1, borderColor: 'rgba(255,255,255,0.13)', backgroundColor: '#071019', padding: 15 },
  pickerCard: { width: '100%', maxWidth: 520, height: '78%', borderRadius: 22, borderWidth: 1, borderColor: '#26394a', backgroundColor: '#071019', padding: 15 },
  resultModal: { width: '100%', maxWidth: 520, borderRadius: 22, borderWidth: 1, borderColor: '#26394a', backgroundColor: '#071019', padding: 16 },
  header: { flexDirection: 'row', alignItems: 'flex-start', gap: 10, marginBottom: 12 },
  flex: { flex: 1 },
  eyebrow: { color: '#8295a6', fontSize: 9, fontWeight: '900', letterSpacing: 1.25 },
  title: { color: '#fff', fontSize: 23, fontWeight: '900', marginTop: 2 },
  modalTitle: { color: '#fff', fontSize: 19, fontWeight: '900', marginTop: 2 },
  subtitle: { color: '#9badbc', fontSize: 11, lineHeight: 16, marginTop: 4 },
  close: { color: '#d3dde6', fontSize: 22, paddingHorizontal: 5 },
  content: { paddingBottom: 20, gap: 12 },
  loading: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 10 },
  muted: { color: '#91a3b3', fontSize: 11, lineHeight: 16 },
  bold: { color: '#fff', fontWeight: '900' },
  ruleCard: { borderRadius: 16, borderWidth: 1, borderColor: 'rgba(255,211,105,0.22)', backgroundColor: 'rgba(255,211,105,0.055)', padding: 13, gap: 6 },
  ruleSeason: { color: '#ffe19a', fontSize: 10, fontWeight: '900', letterSpacing: 1.1 },
  ruleText: { color: '#c4d0da', fontSize: 11, lineHeight: 16 },
  dropRule: { color: '#f1b86f', fontSize: 11, fontWeight: '800', lineHeight: 16 },
  nextRule: { color: '#8ebdff', fontSize: 10, lineHeight: 15 },
  primary: { minHeight: 44, borderRadius: 12, backgroundColor: '#247ce5', alignItems: 'center', justifyContent: 'center', paddingHorizontal: 12 },
  primarySmall: { flex: 1, minHeight: 42, borderRadius: 12, backgroundColor: '#247ce5', alignItems: 'center', justifyContent: 'center', paddingHorizontal: 8 },
  primaryText: { color: '#fff', fontSize: 10, fontWeight: '900', letterSpacing: 0.4 },
  secondary: { flex: 1, minHeight: 42, borderRadius: 12, borderWidth: 1, borderColor: '#31506b', alignItems: 'center', justifyContent: 'center', paddingHorizontal: 8 },
  secondaryText: { color: '#b9d9f6', fontSize: 9, fontWeight: '900' },
  disabled: { opacity: 0.45 },
  pressed: { opacity: 0.68 },
  emptyCard: { borderRadius: 15, borderWidth: 1, borderColor: '#1f3447', padding: 16, alignItems: 'center', gap: 5 },
  emptyTitle: { color: '#fff', fontWeight: '900', fontSize: 15 },
  statusCard: { borderRadius: 14, backgroundColor: 'rgba(255,255,255,0.035)', padding: 12, gap: 5 },
  statusTitle: { color: '#fff', fontWeight: '900', fontSize: 12 },
  warning: { color: '#f0bd72', fontSize: 10, lineHeight: 14 },
  adminRow: { flexDirection: 'row', gap: 8 },
  seedSection: { gap: 6 },
  seedTitle: { color: '#fff', fontSize: 12, fontWeight: '900', marginTop: 3 },
  seedHint: { color: '#8297a9', fontSize: 10, lineHeight: 14, marginBottom: 2 },
  seedRow: { minHeight: 48, borderRadius: 12, backgroundColor: 'rgba(255,255,255,0.035)', borderWidth: 1, borderColor: 'rgba(255,255,255,0.07)', flexDirection: 'row', alignItems: 'center', paddingHorizontal: 10, gap: 10 },
  seedNumber: { color: '#738a9d', width: 23, textAlign: 'center', fontWeight: '900' },
  seedTeam: { color: '#f5f8fb', fontSize: 11, fontWeight: '900' },
  seedSource: { color: '#6f8597', fontSize: 8, marginTop: 2 },
  placeholder: { color: '#687c8d' },
  chevron: { color: '#7892a7', fontSize: 22 },
  competitionTabs: { flexDirection: 'row', gap: 7 },
  tab: { flex: 1, minHeight: 43, borderRadius: 12, borderWidth: 1, borderColor: '#22384b', alignItems: 'center', justifyContent: 'center' },
  tabActive: { backgroundColor: '#edf1f4', borderColor: '#edf1f4' },
  tabText: { color: '#8396a7', fontSize: 9, fontWeight: '900' },
  tabTextActive: { color: '#071019' },
  championCard: { borderRadius: 15, borderWidth: 1, borderColor: 'rgba(255,215,100,0.28)', backgroundColor: 'rgba(255,215,100,0.07)', padding: 13, alignItems: 'center' },
  championEyebrow: { color: '#cba858', fontSize: 8, fontWeight: '900', letterSpacing: 1.4 },
  championTeam: { color: '#fff3be', fontSize: 18, fontWeight: '900', marginTop: 3 },
  bracketHint: { color: '#71889b', fontSize: 9, textAlign: 'center' },
  bracket: { gap: 12, paddingBottom: 5, paddingRight: 10 },
  roundColumn: { width: 252, gap: 7 },
  roundTitle: { color: '#f2f6fa', fontSize: 12, fontWeight: '900' },
  roundSub: { color: '#71889b', fontSize: 9, marginTop: -4 },
  roundMatches: { gap: 8 },
  matchCard: { borderRadius: 13, borderWidth: 1, borderColor: '#1d3244', backgroundColor: '#0a1722', padding: 10, gap: 5 },
  matchFinished: { borderColor: '#2e5b49' },
  matchIndex: { color: '#60798d', fontSize: 7, fontWeight: '900', letterSpacing: 0.8 },
  teamLine: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  matchTeam: { flex: 1, color: '#d7e0e7', fontSize: 10, fontWeight: '800' },
  winner: { color: '#7ce2a4' },
  teamScore: { color: '#fff', width: 24, textAlign: 'center', fontWeight: '900' },
  penaltyText: { color: '#aab8c4', fontSize: 9 },
  advanceText: { color: '#64d692', fontSize: 8, fontWeight: '900' },
  dropText: { color: '#f2b36a', fontSize: 8, fontWeight: '900' },
  resultButton: { marginTop: 3, minHeight: 31, borderRadius: 9, borderWidth: 1, borderColor: '#31506b', alignItems: 'center', justifyContent: 'center' },
  resultButtonText: { color: '#acd4f8', fontSize: 8, fontWeight: '900' },
  pickerContent: { gap: 6, paddingBottom: 12 },
  clubOption: { minHeight: 45, borderRadius: 11, backgroundColor: 'rgba(255,255,255,0.04)', justifyContent: 'center', paddingHorizontal: 12 },
  clubOptionText: { color: '#f0f4f7', fontSize: 11, fontWeight: '900' },
  removeText: { color: '#f28a8f', fontSize: 9, fontWeight: '900', textAlign: 'center' },
  formLabel: { color: '#7f95a8', fontSize: 9, fontWeight: '900', letterSpacing: 0.8, marginTop: 4, marginBottom: 6 },
  scoreInputs: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 },
  scoreField: { flex: 1, alignItems: 'center', gap: 6 },
  inputTeam: { color: '#dce5ec', fontSize: 9, fontWeight: '800', textAlign: 'center' },
  scoreInput: { width: '100%', minHeight: 48, borderRadius: 11, borderWidth: 1, borderColor: '#2b4154', backgroundColor: '#09141e', color: '#fff', fontSize: 22, fontWeight: '900', textAlign: 'center' },
  penInput: { flex: 1, minHeight: 43, borderRadius: 11, borderWidth: 1, borderColor: '#2b4154', backgroundColor: '#09141e', color: '#fff', fontWeight: '900', textAlign: 'center' },
  dash: { color: '#667d90', fontSize: 18, fontWeight: '900' },
  dangerButton: { marginTop: 8, minHeight: 40, borderRadius: 11, borderWidth: 1, borderColor: '#6e3035', alignItems: 'center', justifyContent: 'center' },
  dangerText: { color: '#ff878e', fontSize: 9, fontWeight: '900' },
});
