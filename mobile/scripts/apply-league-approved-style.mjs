import fs from 'node:fs';

const uiPath = new URL('../src/BotParityAppV2.tsx', import.meta.url);
let ui = fs.readFileSync(uiPath, 'utf8');
const marker = '// AJPA_LEAGUE_APPROVED_V3';
if (ui.includes(marker)) process.exit(0);

if (!ui.includes("History, Trophy, Medal")) {
  const reactAnchor = "import React, { ReactNode, useCallback, useEffect, useMemo, useState } from 'react';";
  if (!ui.includes(reactAnchor)) throw new Error('Liga aprobada: import React no encontrado');
  ui = ui.replace(
    reactAnchor,
    reactAnchor + "\nimport { History, Trophy, Medal } from 'lucide-react-native';",
  );
}

const stateAnchor = "  const [leagueData, setLeagueData] = useState<LeagueData | null>(null);";
if (!ui.includes(stateAnchor)) throw new Error('Liga aprobada: falta leagueData');
ui = ui.replace(
  stateAnchor,
  stateAnchor + "\n  const [leagueLoading, setLeagueLoading] = useState(false);\n  const [leagueError, setLeagueError] = useState<string | null>(null);",
);

const openAnchor = '  const openScreen = async (next: Screen) => {';
if (!ui.includes(openAnchor)) throw new Error('Liga aprobada: falta openScreen');

const loader = String.raw`  const loadLeagueData = useCallback(async (showAlert = false) => {
    setLeagueLoading(true);
    setLeagueError(null);
    try {
      const data = await fetchLeague();
      setLeagueData(data);
      return data;
    } catch (error) {
      const message = apiError(error);
      setLeagueError(message);
      if (showAlert) Alert.alert('Liga', message);
      return null;
    } finally {
      setLeagueLoading(false);
    }
  }, []);

`;
ui = ui.replace(openAnchor, loader + openAnchor);

const oldLeagueLoadA = `    if (next === 'league') {
      try { setLeagueData(await fetchLeague()); } catch (error) { Alert.alert('Liga', apiError(error)); }
    }`;
const oldLeagueLoadB = `    if (next === 'league' || next === 'leagueHistory') {
      try { setLeagueData(await fetchLeague()); } catch (error) { Alert.alert('Liga', apiError(error)); }
    }`;
if (ui.includes(oldLeagueLoadB)) {
  ui = ui.replace(oldLeagueLoadB, `    if (next === 'league' || next === 'leagueHistory') {
      await loadLeagueData(true);
    }`);
} else if (ui.includes(oldLeagueLoadA)) {
  ui = ui.replace(oldLeagueLoadA, `    if (next === 'league') {
      await loadLeagueData(true);
    }`);
} else {
  throw new Error('Liga aprobada: no encontré carga de Liga en openScreen');
}

const requireClubAnchor = '  const requireClub = (next: Screen) => {';
if (!ui.includes(requireClubAnchor)) throw new Error('Liga aprobada: falta requireClub');
const hydration = String.raw`  useEffect(() => {
    if (initialScreen === 'league') {
      void loadLeagueData(false);
    }
  }, [initialScreen, loadLeagueData]);

  const refreshLeague = useCallback(async () => {
    await Promise.all([
      loadAll(true),
      loadLeagueData(false),
    ]);
  }, [loadAll, loadLeagueData]);

`;
ui = ui.replace(requireClubAnchor, hydration + requireClubAnchor);

const leagueStart = ui.indexOf('  const leagueScreen = (');
if (leagueStart < 0) throw new Error('Liga aprobada: no encontré leagueScreen');
let leagueEnd = ui.indexOf('\n  const leagueHistoryScreen = (', leagueStart);
if (leagueEnd < 0) leagueEnd = ui.indexOf('\n  const historyScreen = (', leagueStart);
if (leagueEnd < 0) throw new Error('Liga aprobada: no pude aislar leagueScreen');

const leagueScreen = String.raw`  const leagueScreen = (
    <ScrollView
      contentContainerStyle={[s.content, s.leagueApprovedContent]}
      refreshControl={
        <RefreshControl
          refreshing={refreshing || leagueLoading}
          onRefresh={() => { void refreshLeague(); }}
          tintColor={C.blue}
          colors={[C.blue]}
        />
      }
      showsVerticalScrollIndicator={false}
    >
      <View style={s.leagueApprovedHero}>
        <View pointerEvents="none" style={s.leagueApprovedGlow} />
        <View style={s.leagueApprovedHeroTop}>
          <View style={s.leagueApprovedIconTile}>
            <AjpaIcon name="league" size={27} color="#FFFFFF" />
          </View>
          <View style={s.leagueApprovedHeroCopy}>
            <Text style={s.leagueApprovedEyebrow}>LIGA AJPA</Text>
            <Text style={s.leagueApprovedTitle}>
              {leagueData?.cycle?.phase_label ?? snapshot.status.season?.name ?? 'Temporada'}
            </Text>
            <Text style={s.leagueApprovedSubtitle}>Tabla, resultados y goleadores oficiales.</Text>
          </View>
        </View>

        <View style={s.leagueApprovedSummaryRow}>
          <View style={s.leagueApprovedSummaryItem}>
            <Text style={s.leagueApprovedSummaryValue}>{leagueData?.standings.length ?? '—'}</Text>
            <Text style={s.leagueApprovedSummaryLabel}>EQUIPOS</Text>
          </View>
          <View style={s.leagueApprovedSummaryDivider} />
          <View style={s.leagueApprovedSummaryItem}>
            <Text style={s.leagueApprovedSummaryValue}>{leagueData?.scorers?.[0]?.goals ?? '—'}</Text>
            <Text style={s.leagueApprovedSummaryLabel}>MÁX. GOLES</Text>
          </View>
          <View style={s.leagueApprovedSummaryDivider} />
          <View style={s.leagueApprovedSummaryItem}>
            <Text style={s.leagueApprovedSummaryValue}>{leagueData?.matches?.length ?? '—'}</Text>
            <Text style={s.leagueApprovedSummaryLabel}>PARTIDOS</Text>
          </View>
        </View>
      </View>

      <Pressable
        onPress={() => requireClub('leagueHistory')}
        style={({ pressed }) => [s.leagueApprovedHistory, pressed && { opacity: 0.76 }]}
      >
        <View style={s.leagueApprovedHistoryIcon}>
          <History size={24} color="#8ED4FF" strokeWidth={2.1} />
        </View>
        <View style={s.leagueApprovedHistoryCopy}>
          <Text style={s.leagueApprovedHistoryTitle}>Historial de partidos</Text>
          <Text style={s.leagueApprovedHistorySub}>Rivales, marcadores y resultados de tu equipo.</Text>
        </View>
        <View style={s.leagueApprovedArrow}>
          <Text style={s.leagueApprovedArrowText}>›</Text>
        </View>
      </Pressable>

      <View style={s.leagueApprovedSectionHead}>
        <View style={s.leagueApprovedSectionIcon}>
          <Trophy size={17} color="#49B9FF" strokeWidth={2.1} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={s.leagueApprovedSectionEyebrow}>CLASIFICACIÓN</Text>
          <Text style={s.leagueApprovedSectionTitle}>Tabla de posiciones</Text>
        </View>
        {leagueData ? <Text style={s.leagueApprovedUpdated}>EN VIVO</Text> : null}
      </View>

      {leagueLoading && !leagueData ? (
        <View style={s.leagueApprovedLoading}>
          <ActivityIndicator color={C.blue} />
          <Text style={s.leagueApprovedLoadingText}>Cargando tabla oficial…</Text>
        </View>
      ) : null}

      {leagueError && !leagueData ? (
        <View style={s.leagueApprovedError}>
          <Text style={s.leagueApprovedErrorTitle}>No se pudo cargar la Liga</Text>
          <Text style={s.leagueApprovedErrorText}>{leagueError}</Text>
          <Pressable onPress={() => { void loadLeagueData(true); }} style={s.leagueApprovedRetry}>
            <Text style={s.leagueApprovedRetryText}>REINTENTAR</Text>
          </Pressable>
        </View>
      ) : null}

      {leagueData?.standings.length === 0 ? (
        <View style={s.leagueApprovedEmpty}>
          <Text style={s.leagueApprovedEmptyTitle}>Todavía no hay posiciones</Text>
          <Text style={s.leagueApprovedEmptyText}>Cuando se carguen resultados oficiales aparecerán acá.</Text>
        </View>
      ) : null}

      {leagueData?.standings.map((row, index) => {
        const inChampions = index < 16;
        const inEuropa = index >= 16 && index < 24;
        const zoneColor = index === 0 ? '#F0C85A' : inChampions ? '#4BB6FF' : inEuropa ? '#9A79FF' : '#5B7180';
        const zoneLabel = index === 0
          ? 'Campeón · Champions'
          : inChampions
            ? 'Champions AJPA'
            : inEuropa
              ? 'Europa AJPA'
              : '';

        return (
          <View
            key={row.team}
            style={[
              s.leagueApprovedRow,
              { borderLeftColor: teamCardTheme(row.team).border },
            ]}
          >
            <View style={[s.leagueApprovedPosition, index === 0 && s.leagueApprovedPositionFirst]}>
              <Text style={s.leagueApprovedPositionValue}>{index + 1}</Text>
            </View>

            <ClubBadge club={row.team} size={35} style={s.leagueApprovedBadge} />

            <View style={s.leagueApprovedTeamCopy}>
              <Text numberOfLines={1} style={s.leagueApprovedTeam}>{row.team}</Text>
              <Text numberOfLines={1} style={s.leagueApprovedManager}>
                DT: {row.manager_name || 'Sin asignar'}
              </Text>
              <View style={s.leagueApprovedStats}>
                <Text style={s.leagueApprovedStat}>PJ <Text style={s.leagueApprovedStatStrong}>{row.pj}</Text></Text>
                <Text style={s.leagueApprovedStat}>G <Text style={s.leagueApprovedStatStrong}>{row.pg}</Text></Text>
                <Text style={s.leagueApprovedStat}>E <Text style={s.leagueApprovedStatStrong}>{row.pe}</Text></Text>
                <Text style={s.leagueApprovedStat}>P <Text style={s.leagueApprovedStatStrong}>{row.pp}</Text></Text>
                <Text style={s.leagueApprovedStat}>DG <Text style={s.leagueApprovedStatStrong}>{row.dg > 0 ? '+' : ''}{row.dg}</Text></Text>
              </View>
              {zoneLabel ? (
                <View style={s.leagueApprovedZone}>
                  <View style={[s.leagueApprovedZoneDot, { backgroundColor: zoneColor }]} />
                  <Text style={[s.leagueApprovedZoneText, { color: zoneColor }]}>{zoneLabel}</Text>
                </View>
              ) : null}
            </View>

            <View style={s.leagueApprovedPoints}>
              <Text style={[s.leagueApprovedPointsValue, { color: teamCardTheme(row.team).border }]}>{row.pts}</Text>
              <Text style={s.leagueApprovedPointsLabel}>PTS</Text>
            </View>
          </View>
        );
      })}

      <View style={[s.leagueApprovedSectionHead, { marginTop: 8 }]}>
        <View style={s.leagueApprovedSectionIcon}>
          <Medal size={17} color="#49B9FF" strokeWidth={2.1} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={s.leagueApprovedSectionEyebrow}>ESTADÍSTICAS</Text>
          <Text style={s.leagueApprovedSectionTitle}>Top goleadores</Text>
        </View>
      </View>

      {leagueData?.scorers.length === 0 ? (
        <View style={s.leagueApprovedEmpty}>
          <Text style={s.leagueApprovedEmptyTitle}>Todavía no hay goleadores</Text>
          <Text style={s.leagueApprovedEmptyText}>Los goles oficiales aparecerán automáticamente.</Text>
        </View>
      ) : null}

      {leagueData?.scorers.slice(0, 5).map((row, index) => (
        <View style={s.leagueApprovedScorer} key={row.player + '-' + row.team}>
          <View style={[s.leagueApprovedScorerRank, index === 0 && s.leagueApprovedScorerRankFirst]}>
            <Text style={s.leagueApprovedScorerRankText}>{index + 1}</Text>
          </View>
          <ClubBadge club={row.team} size={31} />
          <View style={s.leagueApprovedScorerCopy}>
            <Text numberOfLines={1} style={s.leagueApprovedScorerName}>{row.player}</Text>
            <Text numberOfLines={1} style={s.leagueApprovedScorerClub}>{row.team || 'Sin club'}</Text>
          </View>
          <View style={s.leagueApprovedGoals}>
            <Text style={s.leagueApprovedGoalsValue}>{row.goals}</Text>
            <Text style={s.leagueApprovedGoalsLabel}>GOLES</Text>
          </View>
        </View>
      ))}
    </ScrollView>
  );`;

ui = ui.slice(0, leagueStart) + leagueScreen + ui.slice(leagueEnd);

const sStart = ui.indexOf('const s = StyleSheet.create({');
const styleEnd = sStart < 0 ? -1 : ui.indexOf('\n});', sStart);
if (styleEnd < 0) throw new Error('Liga aprobada: no encontré StyleSheet principal');

const styles = String.raw`
  leagueApprovedContent: { paddingTop: 14, paddingHorizontal: 14, paddingBottom: 118, gap: 10 },
  leagueApprovedHero: { position: 'relative', overflow: 'hidden', minHeight: 174, borderRadius: 22, borderWidth: 1, borderColor: '#245A7C', backgroundColor: '#0A2233', padding: 16 },
  leagueApprovedGlow: { position: 'absolute', width: 230, height: 230, borderRadius: 115, right: -92, top: -104, backgroundColor: 'rgba(47,167,255,0.11)' },
  leagueApprovedHeroTop: { flexDirection: 'row', alignItems: 'center' },
  leagueApprovedIconTile: { width: 55, height: 55, borderRadius: 17, alignItems: 'center', justifyContent: 'center', backgroundColor: '#197FCB', borderWidth: 1, borderColor: '#58BEFF' },
  leagueApprovedHeroCopy: { flex: 1, minWidth: 0, marginLeft: 13 },
  leagueApprovedEyebrow: { color: '#5BC0FF', fontSize: 9.5, fontWeight: '900', letterSpacing: 1.8 },
  leagueApprovedTitle: { color: '#F7FBFF', fontSize: 24, lineHeight: 29, fontWeight: '900', marginTop: 3 },
  leagueApprovedSubtitle: { color: '#8EA4B4', fontSize: 11, lineHeight: 16, marginTop: 3 },
  leagueApprovedSummaryRow: { minHeight: 58, flexDirection: 'row', alignItems: 'center', marginTop: 17, paddingTop: 12, borderTopWidth: 1, borderTopColor: '#24485F' },
  leagueApprovedSummaryItem: { flex: 1, alignItems: 'center' },
  leagueApprovedSummaryDivider: { width: 1, height: 29, backgroundColor: '#28536D' },
  leagueApprovedSummaryValue: { color: '#F7FBFF', fontSize: 18, lineHeight: 21, fontWeight: '900' },
  leagueApprovedSummaryLabel: { color: '#708C9F', fontSize: 7, fontWeight: '900', letterSpacing: 0.9, marginTop: 3 },

  leagueApprovedHistory: { minHeight: 84, borderRadius: 19, borderWidth: 1, borderColor: '#275A7B', backgroundColor: '#0B2537', paddingHorizontal: 13, paddingVertical: 11, flexDirection: 'row', alignItems: 'center' },
  leagueApprovedHistoryIcon: { width: 51, height: 51, borderRadius: 15, borderWidth: 1, borderColor: '#298AC6', backgroundColor: '#0A304A', alignItems: 'center', justifyContent: 'center' },
  leagueApprovedHistoryCopy: { flex: 1, minWidth: 0, marginLeft: 12 },
  leagueApprovedHistoryTitle: { color: '#F5FAFE', fontSize: 16.5, fontWeight: '900' },
  leagueApprovedHistorySub: { color: '#8FA4B4', fontSize: 10.5, lineHeight: 15, marginTop: 4 },
  leagueApprovedArrow: { width: 38, height: 38, borderRadius: 19, borderWidth: 1, borderColor: '#277BAA', backgroundColor: '#081C2A', alignItems: 'center', justifyContent: 'center', marginLeft: 9 },
  leagueApprovedArrowText: { color: '#38B8FF', fontSize: 27, lineHeight: 28, fontWeight: '700' },

  leagueApprovedSectionHead: { minHeight: 52, flexDirection: 'row', alignItems: 'center', marginTop: 4 },
  leagueApprovedSectionIcon: { width: 36, height: 36, borderRadius: 12, backgroundColor: '#0B2A40', borderWidth: 1, borderColor: '#235C7C', alignItems: 'center', justifyContent: 'center', marginRight: 10 },
  leagueApprovedSectionEyebrow: { color: '#4AB8FA', fontSize: 7.5, fontWeight: '900', letterSpacing: 1.35 },
  leagueApprovedSectionTitle: { color: '#F5FAFE', fontSize: 18, lineHeight: 21, fontWeight: '900', marginTop: 2 },
  leagueApprovedUpdated: { color: '#42D885', fontSize: 7.5, fontWeight: '900', letterSpacing: 0.8, borderWidth: 1, borderColor: '#267951', borderRadius: 999, paddingHorizontal: 7, paddingVertical: 4 },

  leagueApprovedLoading: { minHeight: 96, borderRadius: 18, borderWidth: 1, borderColor: '#214B67', backgroundColor: '#091B29', alignItems: 'center', justifyContent: 'center', gap: 9 },
  leagueApprovedLoadingText: { color: '#8EA4B4', fontSize: 10.5, fontWeight: '700' },
  leagueApprovedError: { borderRadius: 18, borderWidth: 1, borderColor: '#8A3846', backgroundColor: '#281018', padding: 15 },
  leagueApprovedErrorTitle: { color: '#FF7D8A', fontSize: 14, fontWeight: '900' },
  leagueApprovedErrorText: { color: '#C7AAB0', fontSize: 10.5, lineHeight: 15, marginTop: 5 },
  leagueApprovedRetry: { alignSelf: 'flex-start', marginTop: 10, borderRadius: 11, backgroundColor: '#159BF3', paddingHorizontal: 13, paddingVertical: 8 },
  leagueApprovedRetryText: { color: '#FFFFFF', fontSize: 9, fontWeight: '900', letterSpacing: 0.7 },
  leagueApprovedEmpty: { borderRadius: 17, borderWidth: 1, borderColor: '#23485F', backgroundColor: '#091C2A', padding: 14 },
  leagueApprovedEmptyTitle: { color: '#F2F7FA', fontSize: 13, fontWeight: '900' },
  leagueApprovedEmptyText: { color: '#8298A8', fontSize: 10.5, lineHeight: 15, marginTop: 4 },

  leagueApprovedRow: { minHeight: 91, flexDirection: 'row', alignItems: 'center', borderRadius: 17, borderWidth: 1, borderLeftWidth: 3, borderColor: '#234B64', backgroundColor: '#0A2030', paddingHorizontal: 10, paddingVertical: 10 },
  leagueApprovedPosition: { width: 33, height: 33, borderRadius: 11, backgroundColor: '#112F43', borderWidth: 1, borderColor: '#2B6587', alignItems: 'center', justifyContent: 'center', marginRight: 8 },
  leagueApprovedPositionFirst: { backgroundColor: '#6E5612', borderColor: '#D8B43D' },
  leagueApprovedPositionValue: { color: '#FFFFFF', fontSize: 13, fontWeight: '900' },
  leagueApprovedBadge: { marginRight: 9 },
  leagueApprovedTeamCopy: { flex: 1, minWidth: 0 },
  leagueApprovedTeam: { color: '#F6FAFD', fontSize: 13.5, lineHeight: 16, fontWeight: '900' },
  leagueApprovedManager: { color: '#7F98AA', fontSize: 8.5, lineHeight: 11, marginTop: 2 },
  leagueApprovedStats: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 5 },
  leagueApprovedStat: { color: '#7891A3', fontSize: 7.8, fontWeight: '700' },
  leagueApprovedStatStrong: { color: '#D8E4EC', fontWeight: '900' },
  leagueApprovedZone: { flexDirection: 'row', alignItems: 'center', marginTop: 5 },
  leagueApprovedZoneDot: { width: 5, height: 5, borderRadius: 3, marginRight: 5 },
  leagueApprovedZoneText: { fontSize: 7.3, lineHeight: 9, fontWeight: '900' },
  leagueApprovedPoints: { width: 43, alignItems: 'center', justifyContent: 'center', marginLeft: 6 },
  leagueApprovedPointsValue: { fontSize: 20, lineHeight: 22, fontWeight: '900' },
  leagueApprovedPointsLabel: { color: '#728A9B', fontSize: 7, fontWeight: '900', letterSpacing: 0.7, marginTop: 2 },

  leagueApprovedScorer: { minHeight: 70, borderRadius: 16, borderWidth: 1, borderColor: '#234B64', backgroundColor: '#0A2030', paddingHorizontal: 10, paddingVertical: 9, flexDirection: 'row', alignItems: 'center' },
  leagueApprovedScorerRank: { width: 31, height: 31, borderRadius: 10, borderWidth: 1, borderColor: '#2C6384', backgroundColor: '#102D40', alignItems: 'center', justifyContent: 'center', marginRight: 9 },
  leagueApprovedScorerRankFirst: { borderColor: '#D8B43D', backgroundColor: '#6E5612' },
  leagueApprovedScorerRankText: { color: '#FFFFFF', fontSize: 12, fontWeight: '900' },
  leagueApprovedScorerCopy: { flex: 1, minWidth: 0, marginLeft: 9 },
  leagueApprovedScorerName: { color: '#F5FAFE', fontSize: 13.5, fontWeight: '900' },
  leagueApprovedScorerClub: { color: '#839BAC', fontSize: 9, marginTop: 3 },
  leagueApprovedGoals: { width: 50, alignItems: 'center' },
  leagueApprovedGoalsValue: { color: '#45B8FF', fontSize: 20, lineHeight: 22, fontWeight: '900' },
  leagueApprovedGoalsLabel: { color: '#728A9B', fontSize: 6.8, fontWeight: '900', letterSpacing: 0.7, marginTop: 2 },
`;

let before = ui.slice(0, styleEnd).trimEnd();
if (!before.endsWith(',')) before += ',';
ui = before + '\n' + styles + ui.slice(styleEnd);
ui += '\n' + marker + '\n';
fs.writeFileSync(uiPath, ui);
console.log('AJPA UI Lab: Liga aprobada aplicada; carga directa, reintento, tabla compacta y goleadores.');
