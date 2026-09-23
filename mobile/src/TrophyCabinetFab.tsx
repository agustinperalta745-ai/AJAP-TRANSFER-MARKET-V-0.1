import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Image,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { apiRequest, fetchLatestHonours } from './api';
import { ClubBadge } from './teamBadges';

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

type LeagueChampionHistoryEntry = {
  competition_id: number;
  competition: string;
  kind: string;
  team: string;
  season_number?: number | null;
  label?: string | null;
  status?: string | null;
  manager?: { user_id?: string | null; username?: string | null; global_name?: string | null } | null;
};

type LeagueChampionsPayload = { champions?: LeagueChampionHistoryEntry[] };

type WinnerRecord = {
  key: TrophyKey;
  season: number | null;
  label: string | null;
  champion: string;
  manager: string | null;
  source: 'archive' | 'officialLeague' | 'current' | 'latest';
};

type RankingMode = 'clubs' | 'managers';

type RankingEntry = {
  id: string;
  name: string;
  total: number;
  league: number;
  champions: number;
  europa: number;
  clubs: string[];
  managers: string[];
};

const TROPHY = {
  league: require('../assets/trophies/liga-ajpa.jpg'),
  champions: require('../assets/trophies/champions-ajpa.jpg'),
  europa: require('../assets/trophies/europa-ajpa.jpg'),
} as const;

const RANKING_TROPHY = {
  league: require('../assets/trophies/ranking-icons/liga-ajpa.jpg'),
  champions: require('../assets/trophies/ranking-icons/champions-ajpa.jpg'),
  europa: require('../assets/trophies/ranking-icons/europa-ajpa.jpg'),
} as const;

const META: Record<TrophyKey, { title: string; eyebrow: string; accent: string; description: string }> = {
  league: {
    title: 'Liga AJPA',
    eyebrow: 'CAMPEÓN DE LIGA',
    accent: '#e5bd68',
    description: 'La competencia principal de la liga.',
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

function isFinishedStatus(value: unknown): boolean {
  const status = normalized(value);
  if (!status) return true; // old archived rows did not always expose a status.
  return ['finished', 'finalizada', 'finalizado', 'completed', 'closed', 'cerrada', 'cerrado'].includes(status);
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
      if (!exact.label && row.label) exact.label = row.label;
      if (row.source === 'officialLeague' || row.source === 'current') exact.source = row.source;
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

function TrophyCount({ trophyKey, count }: { trophyKey: TrophyKey; count: number }) {
  const meta = META[trophyKey];
  return (
    <View style={styles.trophyCount}>
      <Image source={RANKING_TROPHY[trophyKey]} resizeMode="contain" style={styles.trophyCountImage} />
      <View>
        <Text style={styles.trophyCountValue}>{count}</Text>
        <Text style={[styles.trophyCountLabel, { color: meta.accent }]}>
          {trophyKey === 'league' ? 'LIGA' : trophyKey === 'champions' ? 'CHAMPIONS' : 'EUROPA'}
        </Text>
      </View>
    </View>
  );
}

function RankingIdentity({ entry, mode, compact = false }: { entry: RankingEntry; mode: RankingMode; compact?: boolean }) {
  if (mode === 'clubs') {
    return (
      <View style={compact ? styles.podiumBadgeWrap : styles.rankBadgeWrap}>
        <ClubBadge club={entry.name} size={compact ? 42 : 38} />
      </View>
    );
  }

  const initial = entry.name.trim().slice(0, 1).toUpperCase() || 'D';
  return (
    <View style={compact ? styles.podiumManagerAvatar : styles.rankManagerAvatar}>
      <Text style={compact ? styles.podiumManagerInitial : styles.rankManagerInitial}>{initial}</Text>
    </View>
  );
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
      <View style={styles.trophyStage}>
        <Image source={TROPHY[trophyKey]} resizeMode="contain" style={styles.trophyImage} />
      </View>

      <View style={styles.trophyCopy}>
        <Text style={[styles.trophyEyebrow, { color: meta.accent }]}>{meta.eyebrow}</Text>
        <Text style={styles.trophyTitle}>{meta.title}</Text>
        <Text style={styles.trophyDescription}>{meta.description}</Text>

        <View style={styles.latestRow}>
          <View style={styles.latestCopy}>
            <Text style={styles.latestLabel}>ÚLTIMO CAMPEÓN</Text>
            <Text style={styles.latestTeam} numberOfLines={1}>{champion?.champion || 'Aún sin campeón'}</Text>
            {champion?.label ? (
              <Text style={styles.latestSeason}>{champion.label}</Text>
            ) : champion?.season ? (
              <Text style={styles.latestSeason}>Temporada {champion.season}</Text>
            ) : null}
          </View>
          <Text style={[styles.viewHistory, { color: meta.accent }]}>VER PALMARÉS ›</Text>
        </View>
      </View>
    </Pressable>
  );
}

export default function TrophyCabinetScreen({ onClose }: { onClose?: () => void }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [history, setHistory] = useState<ArchivedCompetition[]>([]);
  const [leagueChampions, setLeagueChampions] = useState<LeagueChampionHistoryEntry[]>([]);
  const [cups, setCups] = useState<CupsPayload | null>(null);
  const [honours, setHonours] = useState<Awaited<ReturnType<typeof fetchLatestHonours>> | null>(null);
  const [selected, setSelected] = useState<TrophyKey>('league');
  const [rankingMode, setRankingMode] = useState<RankingMode>('clubs');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    const [historyResult, leagueChampionsResult, cupsResult, honoursResult] = await Promise.allSettled([
      apiRequest<HistoryPayload>('/api/v1/league/seasons'),
      apiRequest<LeagueChampionsPayload>('/api/v1/league/champions-history'),
      apiRequest<CupsPayload>('/api/v1/cups'),
      fetchLatestHonours(),
    ]);

    if (historyResult.status === 'fulfilled') {
      setHistory(Array.isArray(historyResult.value.competitions) ? historyResult.value.competitions : []);
    }
    if (leagueChampionsResult.status === 'fulfilled') {
      setLeagueChampions(Array.isArray(leagueChampionsResult.value.champions) ? leagueChampionsResult.value.champions : []);
    }
    if (cupsResult.status === 'fulfilled') setCups(cupsResult.value);
    if (honoursResult.status === 'fulfilled') setHonours(honoursResult.value);

    if (historyResult.status === 'rejected' && leagueChampionsResult.status === 'rejected' && cupsResult.status === 'rejected' && honoursResult.status === 'rejected') {
      setError('No se pudo cargar el palmarés en este momento.');
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const records = useMemo(() => {
    const rows: WinnerRecord[] = [];

    for (const competition of history) {
      if (!isFinishedStatus(competition.status)) continue;
      const key = classifyCompetition(competition);
      if (!key) continue;
      // Liga/Pretemporada comes only from the FINISHED-only backend feed below.
      // This prevents an active table leader from ever entering the trophy cabinet.
      if (key === 'league') continue;
      const winner = archiveWinner(competition);
      if (!winner) continue;
      rows.push({
        key,
        season: typeof competition.season_number === 'number' ? competition.season_number : null,
        label: clean(competition.label) || null,
        champion: winner.champion,
        manager: winner.manager,
        source: 'archive',
      });
    }

    // League/Pretemporada has a dedicated FINISHED-only backend feed. It resolves
    // the DT that owned the club at the exact competition close time, so historical
    // titles never depend on today's assignment.
    for (const item of leagueChampions) {
      if (!item?.team || !isFinishedStatus(item.status)) continue;
      rows.push({
        key: 'league',
        season: typeof item.season_number === 'number' ? item.season_number : null,
        label: clean(item.label) || clean(item.competition) || null,
        champion: item.team,
        manager: managerName(item.manager),
        source: 'officialLeague',
      });
    }

    const edition = cups?.edition;
    const cupSeason = typeof edition?.season_number === 'number'
      ? edition.season_number
      : (typeof cups?.rules?.season_number === 'number' ? cups.rules.season_number : null);
    const championsChampion = clean(edition?.champions_champion);
    const europaChampion = clean(edition?.europa_champion);
    const cupEditionFinished = isFinishedStatus(edition?.status);
    if (championsChampion && cupEditionFinished) {
      rows.push({ key: 'champions', season: cupSeason, label: cupSeason ? `Temporada ${cupSeason}` : null, champion: championsChampion, manager: null, source: 'current' });
    }
    if (europaChampion && cupEditionFinished) {
      rows.push({ key: 'europa', season: cupSeason, label: cupSeason ? `Temporada ${cupSeason}` : null, champion: europaChampion, manager: null, source: 'current' });
    }

    const leagueLatest = honours?.season_champion;
    if (leagueLatest?.team) {
      rows.push({
        key: 'league',
        season: null,
        label: clean(leagueLatest.competition) || null,
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
          label: clean(cupLatest.competition) || null,
          champion: cupLatest.team,
          manager: managerName(cupLatest.manager),
          source: 'latest',
        });
      }
    }

    return mergeRecords(rows);
  }, [cups, history, honours, leagueChampions]);

  const byCompetition = useMemo(() => ({
    league: records.filter(row => row.key === 'league'),
    champions: records.filter(row => row.key === 'champions'),
    europa: records.filter(row => row.key === 'europa'),
  }), [records]);

  const rankings = useMemo(() => {
    const clubMap = new Map<string, RankingEntry>();
    const managerMap = new Map<string, RankingEntry>();

    const addUnique = (items: string[], value: string | null | undefined) => {
      const next = clean(value);
      if (!next || items.some(item => normalized(item) === normalized(next))) return;
      items.push(next);
    };

    for (const row of records) {
      const clubId = normalized(row.champion);
      if (clubId) {
        const clubEntry = clubMap.get(clubId) ?? {
          id: clubId,
          name: row.champion,
          total: 0,
          league: 0,
          champions: 0,
          europa: 0,
          clubs: [row.champion],
          managers: [],
        };
        clubEntry.total += 1;
        clubEntry[row.key] += 1;
        addUnique(clubEntry.managers, row.manager);
        clubMap.set(clubId, clubEntry);
      }

      if (row.manager) {
        const managerId = normalized(row.manager);
        if (managerId) {
          const managerEntry = managerMap.get(managerId) ?? {
            id: managerId,
            name: row.manager,
            total: 0,
            league: 0,
            champions: 0,
            europa: 0,
            clubs: [],
            managers: [row.manager],
          };
          managerEntry.total += 1;
          managerEntry[row.key] += 1;
          addUnique(managerEntry.clubs, row.champion);
          managerMap.set(managerId, managerEntry);
        }
      }
    }

    const sortRanking = (a: RankingEntry, b: RankingEntry) =>
      b.total - a.total
      || b.champions - a.champions
      || b.league - a.league
      || b.europa - a.europa
      || a.name.localeCompare(b.name, 'es');

    return {
      clubs: [...clubMap.values()].sort(sortRanking),
      managers: [...managerMap.values()].sort(sortRanking),
    };
  }, [records]);

  const rankingRows = rankingMode === 'clubs' ? rankings.clubs : rankings.managers;
  const selectedRows = byCompetition[selected];
  const selectedMeta = META[selected];

  return (
    <Modal
      visible
      animationType="slide"
      presentationStyle="fullScreen"
      statusBarTranslucent={false}
      onRequestClose={onClose}
    >
      <SafeAreaView style={styles.screen} edges={['top', 'bottom', 'left', 'right']}>
        <View style={styles.topBar}>
          <Pressable onPress={onClose} style={({ pressed }) => [styles.backButton, pressed && styles.pressed]}>
            <Text style={styles.backButtonText}>‹ VOLVER</Text>
          </Pressable>
          <View style={styles.topBarCopy}>
            <Text style={styles.topEyebrow}>HISTORIA AJPA</Text>
            <Text style={styles.topTitle}>Vitrina de campeones</Text>
          </View>
        </View>

        <ScrollView
          style={styles.scroll}
          contentContainerStyle={styles.content}
          showsVerticalScrollIndicator
          nestedScrollEnabled
          keyboardShouldPersistTaps="handled"
        >
          <Text style={styles.subtitle}>Las copas oficiales y todos los campeones, ordenados por competencia.</Text>

          <View style={styles.rankingPanel}>
            <View style={styles.rankingHeader}>
              <View style={styles.flex}>
                <Text style={styles.rankingEyebrow}>🏆 HISTORIA AJPA</Text>
                <Text style={styles.rankingTitle}>Ranking de títulos</Text>
                <Text style={styles.rankingSubtitle}>Quiénes construyeron la historia, con cada copa desglosada.</Text>
              </View>
              <View style={styles.totalBadge}>
                <Text style={styles.totalBadgeValue}>{records.length}</Text>
                <Text style={styles.totalBadgeLabel}>TÍTULOS</Text>
              </View>
            </View>

            <View style={styles.rankingTabs}>
              <Pressable
                onPress={() => setRankingMode('clubs')}
                style={({ pressed }) => [styles.rankingTab, rankingMode === 'clubs' && styles.rankingTabActive, pressed && styles.pressed]}
              >
                <Text style={[styles.rankingTabText, rankingMode === 'clubs' && styles.rankingTabTextActive]}>🛡️ CLUBES</Text>
              </Pressable>
              <Pressable
                onPress={() => setRankingMode('managers')}
                style={({ pressed }) => [styles.rankingTab, rankingMode === 'managers' && styles.rankingTabActive, pressed && styles.pressed]}
              >
                <Text style={[styles.rankingTabText, rankingMode === 'managers' && styles.rankingTabTextActive]}>🎩 DTS</Text>
              </Pressable>
            </View>

            {loading && !records.length ? (
              <View style={styles.loadingRow}>
                <ActivityIndicator />
                <Text style={styles.muted}>Armando el ranking histórico…</Text>
              </View>
            ) : rankingRows.length ? (
              <>
                <Text style={styles.podiumHeading}>PODIO HISTÓRICO</Text>
                <View style={styles.podiumRow}>
                  {rankingRows.slice(0, 3).map((entry, index) => (
                    <View key={entry.id} style={[styles.podiumCard, index === 0 && styles.podiumFirst]}>
                      <Text style={styles.podiumPosition}>{index === 0 ? '🥇' : index === 1 ? '🥈' : '🥉'}</Text>
                      <RankingIdentity entry={entry} mode={rankingMode} compact />
                      <Text style={styles.podiumName} numberOfLines={2}>{entry.name}</Text>
                      <Text style={styles.podiumTotal}>{entry.total}</Text>
                      <Text style={styles.podiumTotalLabel}>{entry.total === 1 ? 'TÍTULO' : 'TÍTULOS'}</Text>
                    </View>
                  ))}
                </View>

                <Text style={styles.fullRankingHeading}>CLASIFICACIÓN COMPLETA</Text>
                <View style={styles.rankingList}>
                  {rankingRows.map((entry, index) => (
                    <View key={entry.id} style={styles.rankRow}>
                      <View style={styles.rankMain}>
                        <View style={styles.rankPositionWrap}>
                          <Text style={styles.rankPosition}>{index + 1}</Text>
                        </View>
                        <RankingIdentity entry={entry} mode={rankingMode} />
                        <View style={styles.rankCopy}>
                          <Text style={styles.rankName} numberOfLines={1}>{entry.name}</Text>
                          <Text style={styles.rankMeta} numberOfLines={2}>
                            {rankingMode === 'clubs'
                              ? (entry.managers.length ? `DT: ${entry.managers.join(' · ')}` : 'DT histórico no registrado')
                              : (entry.clubs.length ? `Clubes: ${entry.clubs.join(' · ')}` : 'Club no registrado')}
                          </Text>
                        </View>
                        <View style={styles.rankTotal}>
                          <Text style={styles.rankTotalValue}>{entry.total}</Text>
                          <Text style={styles.rankTotalLabel}>{entry.total === 1 ? 'TÍTULO' : 'TÍTULOS'}</Text>
                        </View>
                      </View>

                      <View style={styles.trophyCountsRow}>
                        <TrophyCount trophyKey="league" count={entry.league} />
                        <TrophyCount trophyKey="champions" count={entry.champions} />
                        <TrophyCount trophyKey="europa" count={entry.europa} />
                      </View>
                    </View>
                  ))}
                </View>

                <Text style={styles.rankingRule}>Orden: títulos totales · desempate por Champions, Liga y Europa.</Text>
              </>
            ) : (
              <View style={styles.emptyState}>
                <Text style={styles.emptyIcon}>🏆</Text>
                <Text style={styles.emptyTitle}>Todavía no hay títulos para rankear</Text>
                <Text style={styles.muted}>El ranking se completa automáticamente cuando se cierren competencias oficiales.</Text>
              </View>
            )}
          </View>

          <Text style={styles.sectionDividerTitle}>PALMARÉS POR COMPETENCIA</Text>

          <TrophyCard trophyKey="league" selected={selected === 'league'} champion={byCompetition.league[0] || null} onPress={() => setSelected('league')} />
          <TrophyCard trophyKey="champions" selected={selected === 'champions'} champion={byCompetition.champions[0] || null} onPress={() => setSelected('champions')} />
          <TrophyCard trophyKey="europa" selected={selected === 'europa'} champion={byCompetition.europa[0] || null} onPress={() => setSelected('europa')} />

          <View style={[styles.historyPanel, { borderColor: `${selectedMeta.accent}66` }]}>
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
                    <ClubBadge club={row.champion} size={34} />
                  </View>
                  <View style={styles.flex}>
                    <Text style={styles.winnerSeason}>{row.label ? row.label.toUpperCase() : row.season ? `TEMPORADA ${row.season}` : 'REGISTRO OFICIAL'}</Text>
                    <Text style={styles.winnerTeam}>{row.champion}</Text>
                    {row.manager ? <Text style={styles.winnerManager}>DT: {row.manager}</Text> : <Text style={styles.winnerManagerMuted}>DT no registrado</Text>}
                  </View>
                  {index === 0 ? <Text style={[styles.latestTag, { color: selectedMeta.accent }]}>ÚLTIMO</Text> : null}
                </View>
              ))
            ) : (
              <View style={styles.emptyState}>
                <Text style={styles.emptyIcon}>🏆</Text>
                <Text style={styles.emptyTitle}>Todavía no hay campeón archivado</Text>
                <Text style={styles.muted}>Cuando haya un ganador oficial, va a aparecer automáticamente acá.</Text>
              </View>
            )}

            {error ? (
              <Pressable onPress={() => void load()} style={styles.retryButton}>
                <Text style={styles.errorText}>{error} · TOCAR PARA REINTENTAR</Text>
              </Pressable>
            ) : null}
          </View>

          <Text style={styles.footerNote}>La vitrina se alimenta del historial oficial de Liga, Champions AJPA y Europa AJPA.</Text>
        </ScrollView>
      </SafeAreaView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: '#03080d' },
  topBar: {
    minHeight: 70,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#172633',
    backgroundColor: '#050c12',
  },
  backButton: {
    minHeight: 42,
    paddingHorizontal: 13,
    borderRadius: 13,
    borderWidth: 1,
    borderColor: '#2a5372',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#08141e',
  },
  backButtonText: { color: '#8ac5ff', fontSize: 10, fontWeight: '900', letterSpacing: 0.8 },
  topBarCopy: { flex: 1, minWidth: 0 },
  topEyebrow: { color: '#b49a65', fontSize: 8, fontWeight: '900', letterSpacing: 1.4 },
  topTitle: { color: '#fff', fontSize: 21, fontWeight: '900', marginTop: 1 },
  scroll: { flex: 1 },
  content: { padding: 14, paddingBottom: 46, gap: 12 },
  subtitle: { color: '#94a4b2', fontSize: 11.5, lineHeight: 17, marginBottom: 1 },
  flex: { flex: 1, minWidth: 0 },
  pressed: { opacity: 0.7 },
  trophyCard: {
    borderRadius: 20,
    borderWidth: 1.5,
    borderColor: 'rgba(255,255,255,0.12)',
    overflow: 'hidden',
    backgroundColor: '#0b131a',
  },
  trophyStage: {
    height: 132,
    width: '100%',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#05090d',
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255,255,255,0.07)',
    paddingVertical: 10,
  },
  trophyImage: {
    width: 116,
    height: 116,
    borderRadius: 10,
  },
  trophyCopy: { paddingHorizontal: 15, paddingTop: 12, paddingBottom: 13 },
  trophyEyebrow: { fontSize: 8, fontWeight: '900', letterSpacing: 1.2 },
  trophyTitle: { color: '#fff', fontSize: 20, fontWeight: '900', marginTop: 2 },
  trophyDescription: { color: '#c6d0d8', fontSize: 10.5, lineHeight: 15, marginTop: 3 },
  latestRow: {
    marginTop: 10,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.10)',
    backgroundColor: '#050a0f',
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  latestCopy: { flex: 1, minWidth: 0 },
  latestLabel: { color: '#788b9a', fontSize: 7, fontWeight: '900', letterSpacing: 0.75 },
  latestTeam: { color: '#fff', fontSize: 13, fontWeight: '900', marginTop: 2 },
  latestSeason: { color: '#a9b6c0', fontSize: 8.5, marginTop: 1 },
  viewHistory: { fontSize: 7.5, fontWeight: '900', letterSpacing: 0.4 },
  historyPanel: {
    borderRadius: 19,
    borderWidth: 1,
    backgroundColor: '#08121b',
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
    minHeight: 70,
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
  winnerSeason: { color: '#788d9f', fontSize: 7, fontWeight: '900', letterSpacing: 0.8 },
  winnerTeam: { color: '#fff', fontSize: 14, fontWeight: '900', marginTop: 1 },
  winnerManager: { color: '#b4c0c9', fontSize: 9, marginTop: 2, fontWeight: '700' },
  winnerManagerMuted: { color: '#617384', fontSize: 8, marginTop: 2 },
  latestTag: { fontSize: 7, fontWeight: '900', letterSpacing: 0.6 },
  emptyState: { minHeight: 116, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 16, gap: 4 },
  emptyIcon: { fontSize: 28 },
  emptyTitle: { color: '#eef3f6', fontSize: 13, fontWeight: '900', textAlign: 'center' },
  retryButton: { marginTop: 2, paddingVertical: 8 },
  errorText: { color: '#efa2a2', fontSize: 8.5, lineHeight: 13, textAlign: 'center', fontWeight: '800' },
  rankingPanel: {
    borderRadius: 22,
    borderWidth: 1,
    borderColor: '#5b4822',
    backgroundColor: '#0a1015',
    padding: 13,
    gap: 10,
  },
  rankingHeader: { flexDirection: 'row', alignItems: 'flex-start', gap: 10 },
  rankingEyebrow: { color: '#e5bd68', fontSize: 8, fontWeight: '900', letterSpacing: 1.3 },
  rankingTitle: { color: '#fff', fontSize: 23, fontWeight: '900', marginTop: 2 },
  rankingSubtitle: { color: '#96a6b3', fontSize: 10, lineHeight: 14, marginTop: 3 },
  totalBadge: {
    minWidth: 56,
    minHeight: 56,
    borderRadius: 15,
    borderWidth: 1,
    borderColor: '#80672f',
    backgroundColor: '#151207',
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 8,
  },
  totalBadgeValue: { color: '#f2d68c', fontSize: 18, fontWeight: '900', lineHeight: 20 },
  totalBadgeLabel: { color: '#a58d57', fontSize: 6.5, fontWeight: '900', letterSpacing: 0.8, marginTop: 2 },
  rankingTabs: { flexDirection: 'row', gap: 7 },
  rankingTab: {
    flex: 1,
    minHeight: 38,
    borderRadius: 11,
    borderWidth: 1,
    borderColor: '#273644',
    backgroundColor: '#081019',
    alignItems: 'center',
    justifyContent: 'center',
  },
  rankingTabActive: { borderColor: '#b3924f', backgroundColor: '#17150c' },
  rankingTabText: { color: '#778998', fontSize: 9, fontWeight: '900', letterSpacing: 0.65 },
  rankingTabTextActive: { color: '#f1d38a' },
  podiumHeading: { color: '#b9c5ce', fontSize: 8, fontWeight: '900', letterSpacing: 1.2, marginTop: 1 },
  podiumRow: { flexDirection: 'row', gap: 7, alignItems: 'stretch' },
  podiumCard: {
    flex: 1,
    minWidth: 0,
    minHeight: 154,
    borderRadius: 15,
    borderWidth: 1,
    borderColor: '#2b3a46',
    backgroundColor: '#09121a',
    alignItems: 'center',
    paddingHorizontal: 7,
    paddingVertical: 10,
  },
  podiumFirst: { borderColor: '#b59650', backgroundColor: '#17140b' },
  podiumPosition: { fontSize: 18, marginBottom: 5 },
  podiumBadgeWrap: { width: 46, height: 46, alignItems: 'center', justifyContent: 'center' },
  podiumManagerAvatar: {
    width: 44,
    height: 44,
    borderRadius: 22,
    borderWidth: 1,
    borderColor: '#b59650',
    backgroundColor: '#171e25',
    alignItems: 'center',
    justifyContent: 'center',
  },
  podiumManagerInitial: { color: '#f1d38a', fontSize: 19, fontWeight: '900' },
  podiumName: { color: '#fff', fontSize: 10, lineHeight: 13, fontWeight: '900', textAlign: 'center', minHeight: 27, marginTop: 5 },
  podiumTotal: { color: '#f1d38a', fontSize: 22, fontWeight: '900', lineHeight: 23, marginTop: 5 },
  podiumTotalLabel: { color: '#93825d', fontSize: 6.5, fontWeight: '900', letterSpacing: 0.8, marginTop: 2 },
  fullRankingHeading: { color: '#b9c5ce', fontSize: 8, fontWeight: '900', letterSpacing: 1.2, marginTop: 2 },
  rankingList: { gap: 8 },
  rankRow: {
    borderRadius: 14,
    borderWidth: 1,
    borderColor: '#22313d',
    backgroundColor: '#071018',
    padding: 10,
  },
  rankMain: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  rankPositionWrap: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: '#121d26',
    borderWidth: 1,
    borderColor: '#314352',
    alignItems: 'center',
    justifyContent: 'center',
  },
  rankPosition: { color: '#b7c4ce', fontSize: 10, fontWeight: '900' },
  rankBadgeWrap: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  rankManagerAvatar: {
    width: 38,
    height: 38,
    borderRadius: 19,
    borderWidth: 1,
    borderColor: '#3a5367',
    backgroundColor: '#101b24',
    alignItems: 'center',
    justifyContent: 'center',
  },
  rankManagerInitial: { color: '#9dc8ee', fontSize: 16, fontWeight: '900' },
  rankCopy: { flex: 1, minWidth: 0 },
  rankName: { color: '#fff', fontSize: 13, fontWeight: '900' },
  rankMeta: { color: '#7f93a3', fontSize: 8, lineHeight: 11, marginTop: 2 },
  rankTotal: { minWidth: 47, alignItems: 'flex-end' },
  rankTotalValue: { color: '#f1d38a', fontSize: 20, fontWeight: '900', lineHeight: 21 },
  rankTotalLabel: { color: '#8a7a55', fontSize: 6, fontWeight: '900', letterSpacing: 0.65 },
  trophyCountsRow: { flexDirection: 'row', gap: 6, marginTop: 9 },
  trophyCount: {
    flex: 1,
    minWidth: 0,
    minHeight: 42,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#1e2e3b',
    backgroundColor: '#050b10',
    paddingHorizontal: 6,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
  },
  trophyCountImage: { width: 26, height: 26, borderRadius: 4 },
  trophyCountValue: { color: '#fff', fontSize: 12, fontWeight: '900', lineHeight: 13 },
  trophyCountLabel: { fontSize: 5.5, fontWeight: '900', letterSpacing: 0.35, marginTop: 1 },
  rankingRule: { color: '#667988', fontSize: 7.5, lineHeight: 11, textAlign: 'center' },
  sectionDividerTitle: { color: '#b49a65', fontSize: 9, fontWeight: '900', letterSpacing: 1.35, marginTop: 5 },
  footerNote: { color: '#647889', fontSize: 9, lineHeight: 13, textAlign: 'center', paddingHorizontal: 14, paddingTop: 2 },
});