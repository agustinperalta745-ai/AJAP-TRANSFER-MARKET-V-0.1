import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Image,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { apiRequest, fetchLatestHonours } from './api';

type TrophyKey = 'league' | 'champions' | 'europa';

type ArchivedStanding = {
  team?: string | null;
  team_name?: string | null;
  position?: number | null;
  manager_name?: string | null;
  manager?: string | { username?: string | null; global_name?: string | null } | null;
};

type ArchivedCompetition = {
  id?: number | string;
  kind?: string | null;
  season_number?: number | null;
  label?: string | null;
  status?: string | null;
  standings?: ArchivedStanding[] | null;
  champion?: string | null;
  champion_team?: string | null;
  winner?: string | null;
  winner_team?: string | null;
  manager_name?: string | null;
  champion_manager?: string | null;
};

type HistoryPayload = { competitions?: ArchivedCompetition[] };

type CupEdition = {
  season_number?: number | null;
  status?: string | null;
  champions_champion?: string | null;
  europa_champion?: string | null;
};

type CupsPayload = {
  rules?: { season_number?: number | null } | null;
  edition?: CupEdition | null;
};

type WinnerRecord = {
  key: TrophyKey;
  season: number | null;
  champion: string;
  manager: string | null;
  source: 'archive' | 'current' | 'latest';
};

const TROPHY = {
  league: require('../assets/trophies/liga-ajpa.jpg'),
  champions: require('../assets/trophies/champions-ajpa.jpg'),
  europa: require('../assets/trophies/europa-ajpa.jpg'),
} as const;

const META: Record<TrophyKey, { title: string; eyebrow: string; accent: string; description: string }> = {
  league: {
    title: 'Liga AJPA',
    eyebrow: 'CAMPEÓN DE LIGA',
    accent: '#e5bd68',
    description: 'El campeón de la competencia principal de liga.',
  },
  champions: {
    title: 'Champions AJPA',
    eyebrow: 'MÁXIMA COPA',
    accent: '#88b8ff',
    description: 'La copa internacional más prestigiosa de AJPA.',
  },
  europa: {
    title: 'Europa AJPA',
    eyebrow: 'COPA EUROPA',
    accent: '#e7a15c',
    description: 'El segundo gran torneo internacional de AJPA.',
  },
};

function clean(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

function normalized(value: unknown): string {
  return clean(value)
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase();
}

function classifyCompetition(row: ArchivedCompetition): TrophyKey | null {
  const text = normalized(`${row.kind ?? ''} ${row.label ?? ''}`);
  if (text.includes('champions')) return 'champions';
  if (text.includes('europa')) return 'europa';
  if (text.includes('liga') || text.includes('league') || text.includes('temporada') || text.includes('season')) return 'league';
  return null;
}

function standingTeam(row: ArchivedStanding | undefined): string {
  return clean(row?.team) || clean(row?.team_name);
}

function standingManager(row: ArchivedStanding | undefined): string | null {
  const direct = clean(row?.manager_name);
  if (direct) return direct;
  if (typeof row?.manager === 'string') return clean(row.manager) || null;
  if (row?.manager && typeof row.manager === 'object') {
    return clean(row.manager.global_name) || clean(row.manager.username) || null;
  }
  return null;
}

function archiveWinner(row: ArchivedCompetition): { champion: string; manager: string | null } | null {
  const explicit = clean(row.champion_team) || clean(row.champion) || clean(row.winner_team) || clean(row.winner);
  const standings = Array.isArray(row.standings) ? [...row.standings] : [];
  standings.sort((a, b) => {
    const pa = typeof a.position === 'number' ? a.position : Number.MAX_SAFE_INTEGER;
    const pb = typeof b.position === 'number' ? b.position : Number.MAX_SAFE_INTEGER;
    return pa - pb;
  });
  const top = standings.find(item => Boolean(standingTeam(item)));
  const champion = explicit || standingTeam(top);
  if (!champion) return null;

  const championStanding = standings.find(item => normalized(standingTeam(item)) === normalized(champion)) || top;
  const manager = clean(row.champion_manager) || clean(row.manager_name) || standingManager(championStanding);
  return { champion, manager: manager || null };
}

function managerName(value: unknown): string | null {
  if (!value || typeof value !== 'object') return null;
  const manager = value as { username?: string | null; global_name?: string | null };
  return clean(manager.global_name) || clean(manager.username) || null;
}

function mergeRecords(rows: WinnerRecord[]): WinnerRecord[] {
  const result: WinnerRecord[] = [];

  for (const row of rows) {
    const exact = result.find(item =>
      item.key === row.key
      && item.season === row.season
      && normalized(item.champion) === normalized(row.champion),
    );
    if (exact) {
      if (!exact.manager && row.manager) exact.manager = row.manager;
      if (row.source === 'current') exact.source = 'current';
      continue;
    }

    if (row.source === 'latest' && row.season === null) {
      const sameChampion = result.find(item =>
        item.key === row.key && normalized(item.champion) === normalized(row.champion),
      );
      if (sameChampion) {
        if (!sameChampion.manager && row.manager) sameChampion.manager = row.manager;
        continue;
      }
    }

    result.push({ ...row });
  }

  return result.sort((a, b) => {
    if (a.season === null && b.season === null) return a.champion.localeCompare(b.champion);
    if (a.season === null) return 1;
    if (b.season === null) return -1;
    return b.season - a.season;
  });
}

function TrophyCard({
  trophyKey,
  selected,
  champion,
  onPress,
}: {
  trophyKey: TrophyKey;
  selected: boolean;
  champion: WinnerRecord | null;
  onPress: () => void;
}) {
  const meta = META[trophyKey];
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [
        styles.trophyCard,
        selected && { borderColor: meta.accent },
        pressed && styles.pressed,
      ]}
    >
      <View style={styles.trophyVisual}>
        <Image source={TROPHY[trophyKey]} resizeMode="contain" style={styles.trophyImage} />
      </View>
      <View style={styles.trophyCopy}>
        <Text style={[styles.trophyEyebrow, { color: meta.accent }]}>{meta.eyebrow}</Text>
        <Text style={styles.trophyTitle}>{meta.title}</Text>
        <Text style={styles.trophyDescription}>{meta.description}</Text>
        <View style={styles.latestPill}>
          <Text style={styles.latestPillLabel}>ÚLTIMO CAMPEÓN</Text>
          <Text style={styles.latestPillTeam} numberOfLines={2}>{champion?.champion || 'Aún sin campeón registrado'}</Text>
          {champion?.season ? <Text style={styles.latestPillSeason}>Temporada {champion.season}</Text> : null}
        </View>
      </View>
    </Pressable>
  );
}

export default function TrophyCabinetScreen() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [history, setHistory] = useState<ArchivedCompetition[]>([]);
  const [cups, setCups] = useState<CupsPayload | null>(null);
  const [honours, setHonours] = useState<Awaited<ReturnType<typeof fetchLatestHonours>> | null>(null);
  const [selected, setSelected] = useState<TrophyKey>('league');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    const [historyResult, cupsResult, honoursResult] = await Promise.allSettled([
      apiRequest<HistoryPayload>('/api/v1/league/seasons'),
      apiRequest<CupsPayload>('/api/v1/cups'),
      fetchLatestHonours(),
    ]);

    if (historyResult.status === 'fulfilled') {
      setHistory(Array.isArray(historyResult.value.competitions) ? historyResult.value.competitions : []);
    }
    if (cupsResult.status === 'fulfilled') setCups(cupsResult.value);
    if (honoursResult.status === 'fulfilled') setHonours(honoursResult.value);

    if (historyResult.status === 'rejected' && cupsResult.status === 'rejected' && honoursResult.status === 'rejected') {
      setError('No se pudo cargar el palmarés en este momento. Las copas oficiales siguen disponibles en la vitrina.');
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const records = useMemo(() => {
    const rows: WinnerRecord[] = [];

    for (const competition of history) {
      const key = classifyCompetition(competition);
      if (!key) continue;
      const winner = archiveWinner(competition);
      if (!winner) continue;
      rows.push({
        key,
        season: typeof competition.season_number === 'number' ? competition.season_number : null,
        champion: winner.champion,
        manager: winner.manager,
        source: 'archive',
      });
    }

    const edition = cups?.edition;
    const cupSeason = typeof edition?.season_number === 'number'
      ? edition.season_number
      : (typeof cups?.rules?.season_number === 'number' ? cups.rules.season_number : null);
    const championsChampion = clean(edition?.champions_champion);
    const europaChampion = clean(edition?.europa_champion);
    if (championsChampion) {
      rows.push({ key: 'champions', season: cupSeason, champion: championsChampion, manager: null, source: 'current' });
    }
    if (europaChampion) {
      rows.push({ key: 'europa', season: cupSeason, champion: europaChampion, manager: null, source: 'current' });
    }

    const leagueLatest = honours?.season_champion;
    if (leagueLatest?.team) {
      rows.push({
        key: 'league',
        season: null,
        champion: leagueLatest.team,
        manager: managerName(leagueLatest.manager),
        source: 'latest',
      });
    }

    const cupLatest = honours?.cup_champion;
    if (cupLatest?.team) {
      const key = classifyCompetition({ kind: cupLatest.kind, label: cupLatest.competition });
      if (key === 'champions' || key === 'europa') {
        rows.push({
          key,
          season: null,
          champion: cupLatest.team,
          manager: managerName(cupLatest.manager),
          source: 'latest',
        });
      }
    }

    return mergeRecords(rows);
  }, [cups, history, honours]);

  const byCompetition = useMemo(() => ({
    league: records.filter(row => row.key === 'league'),
    champions: records.filter(row => row.key === 'champions'),
    europa: records.filter(row => row.key === 'europa'),
  }), [records]);

  const selectedRows = byCompetition[selected];
  const selectedMeta = META[selected];

  return (
    <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.content}>
      <View style={styles.header}>
        <Text style={styles.eyebrow}>HISTORIA AJPA</Text>
        <Text style={styles.title}>Vitrina de campeones</Text>
        <Text style={styles.subtitle}>Trofeos oficiales y campeones históricos de cada competencia.</Text>
      </View>

      <TrophyCard trophyKey="league" selected={selected === 'league'} champion={byCompetition.league[0] || null} onPress={() => setSelected('league')} />
      <TrophyCard trophyKey="champions" selected={selected === 'champions'} champion={byCompetition.champions[0] || null} onPress={() => setSelected('champions')} />
      <TrophyCard trophyKey="europa" selected={selected === 'europa'} champion={byCompetition.europa[0] || null} onPress={() => setSelected('europa')} />

      <View style={[styles.historyPanel, { borderColor: `${selectedMeta.accent}55` }]}>
        <View style={styles.historyHeader}>
          <View style={styles.flex}>
            <Text style={[styles.historyEyebrow, { color: selectedMeta.accent }]}>PALMARÉS OFICIAL</Text>
            <Text style={styles.historyTitle}>{selectedMeta.title}</Text>
          </View>
          <Text style={styles.titleCount}>{selectedRows.length} {selectedRows.length === 1 ? 'título' : 'títulos'}</Text>
        </View>

        {loading && !records.length ? (
          <View style={styles.loadingRow}>
            <ActivityIndicator />
            <Text style={styles.muted}>Cargando campeones…</Text>
          </View>
        ) : selectedRows.length ? (
          selectedRows.map((row, index) => (
            <View key={`${row.key}-${row.season ?? 'latest'}-${row.champion}-${index}`} style={styles.winnerRow}>
              <View style={[styles.medal, { borderColor: `${selectedMeta.accent}88` }]}>
                <Text style={[styles.medalText, { color: selectedMeta.accent }]}>★</Text>
              </View>
              <View style={styles.flex}>
                <Text style={styles.winnerSeason}>{row.season ? `TEMPORADA ${row.season}` : 'REGISTRO OFICIAL'}</Text>
                <Text style={styles.winnerTeam}>{row.champion}</Text>
                {row.manager ? <Text style={styles.winnerManager}>DT: {row.manager}</Text> : <Text style={styles.winnerManagerMuted}>DT no registrado en este historial</Text>}
              </View>
              {index === 0 ? <Text style={[styles.latestTag, { color: selectedMeta.accent }]}>ÚLTIMO</Text> : null}
            </View>
          ))
        ) : (
          <View style={styles.emptyState}>
            <Text style={styles.emptyIcon}>🏆</Text>
            <Text style={styles.emptyTitle}>Todavía no hay campeón archivado</Text>
            <Text style={styles.muted}>Cuando esta competencia tenga un ganador oficial, va a quedar guardado acá.</Text>
          </View>
        )}

        {error ? <Text style={styles.errorText}>{error}</Text> : null}
      </View>

      <Text style={styles.footerNote}>La vitrina se alimenta del historial oficial de temporadas y de las copas AJPA.</Text>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: { padding: 16, paddingBottom: 36, gap: 12 },
  header: { marginBottom: 2 },
  flex: { flex: 1, minWidth: 0 },
  eyebrow: { color: '#b49a65', fontSize: 9, fontWeight: '900', letterSpacing: 1.55 },
  title: { color: '#fff', fontSize: 27, fontWeight: '900', marginTop: 2 },
  subtitle: { color: '#94a4b2', fontSize: 11.5, lineHeight: 17, marginTop: 4 },
  pressed: { opacity: 0.7 },
  trophyCard: {
    minHeight: 194,
    flexDirection: 'row',
    alignItems: 'stretch',
    borderRadius: 18,
    borderWidth: 1.5,
    borderColor: 'rgba(255,255,255,0.11)',
    overflow: 'hidden',
    backgroundColor: 'rgba(12,19,26,0.95)',
  },
  trophyVisual: {
    width: '40%',
    minHeight: 194,
    backgroundColor: '#05080c',
    alignItems: 'center',
    justifyContent: 'center',
    borderRightWidth: 1,
    borderRightColor: 'rgba(255,255,255,0.08)',
    paddingVertical: 20,
    paddingHorizontal: 14,
  },
  trophyImage: {
    width: '82%',
    height: '82%',
    borderRadius: 10,
  },
  trophyCopy: { flex: 1, padding: 14, justifyContent: 'center' },
  trophyEyebrow: { fontSize: 8, fontWeight: '900', letterSpacing: 1.25 },
  trophyTitle: { color: '#fff', fontSize: 20, fontWeight: '900', marginTop: 2 },
  trophyDescription: { color: '#d0d8df', fontSize: 10, lineHeight: 14, marginTop: 3 },
  latestPill: {
    marginTop: 9,
    alignSelf: 'flex-start',
    maxWidth: '100%',
    borderRadius: 10,
    backgroundColor: 'rgba(3,7,10,0.76)',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.12)',
    paddingHorizontal: 9,
    paddingVertical: 6,
  },
  latestPillLabel: { color: '#8293a2', fontSize: 7, fontWeight: '900', letterSpacing: 0.8 },
  latestPillTeam: { color: '#fff', fontSize: 12, fontWeight: '900', marginTop: 1 },
  latestPillSeason: { color: '#aebac3', fontSize: 8, marginTop: 1 },
  historyPanel: {
    marginTop: 3,
    borderRadius: 18,
    borderWidth: 1,
    backgroundColor: 'rgba(8,18,27,0.96)',
    padding: 13,
    gap: 8,
  },
  historyHeader: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 2 },
  historyEyebrow: { fontSize: 8, fontWeight: '900', letterSpacing: 1.3 },
  historyTitle: { color: '#fff', fontSize: 19, fontWeight: '900', marginTop: 2 },
  titleCount: { color: '#9dacb9', fontSize: 9, fontWeight: '800' },
  loadingRow: { minHeight: 96, alignItems: 'center', justifyContent: 'center', gap: 8 },
  muted: { color: '#8fa0ae', fontSize: 10, lineHeight: 15, textAlign: 'center' },
  winnerRow: {
    minHeight: 72,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    borderRadius: 13,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.07)',
    backgroundColor: 'rgba(255,255,255,0.035)',
    padding: 10,
  },
  medal: { width: 36, height: 36, borderRadius: 18, borderWidth: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(255,255,255,0.03)' },
  medalText: { fontSize: 17, fontWeight: '900' },
  winnerSeason: { color: '#788d9f', fontSize: 7, fontWeight: '900', letterSpacing: 0.8 },
  winnerTeam: { color: '#fff', fontSize: 14, fontWeight: '900', marginTop: 1 },
  winnerManager: { color: '#b4c0c9', fontSize: 9, marginTop: 2, fontWeight: '700' },
  winnerManagerMuted: { color: '#617384', fontSize: 8, marginTop: 2 },
  latestTag: { fontSize: 7, fontWeight: '900', letterSpacing: 0.6 },
  emptyState: { minHeight: 126, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 16, gap: 4 },
  emptyIcon: { fontSize: 28 },
  emptyTitle: { color: '#eef3f6', fontSize: 13, fontWeight: '900', textAlign: 'center' },
  errorText: { color: '#efa2a2', fontSize: 9, lineHeight: 14, textAlign: 'center', marginTop: 3 },
  footerNote: { color: '#647889', fontSize: 9, lineHeight: 13, textAlign: 'center', paddingHorizontal: 14, paddingTop: 2 },
});