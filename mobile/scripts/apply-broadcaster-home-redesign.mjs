import fs from 'node:fs';

const uiPath = new URL('../src/BotParityAppV2.tsx', import.meta.url);
let ui = fs.readFileSync(uiPath, 'utf8');

const START = `  const home = (`;
const END = `  const clubMenu = (`;
const start = ui.indexOf(START);
const end = ui.indexOf(END, start + START.length);
if (start < 0 || end < 0) {
  throw new Error('AJPA Broadcaster: no encontré el bloque de Inicio');
}

const home = String.raw`  // AJPA BROADCASTER HOME V1
  const home = (
    <ScrollView
      contentContainerStyle={[s.content, s.bcContent]}
      refreshControl={refreshControl}
      showsVerticalScrollIndicator={false}
    >
      <View style={s.bcBrandRow}>
        <View style={s.bcBrandMain}>
          <Text style={s.bcBrand}>AJPA</Text>
          <View style={s.bcBrandRule} />
          <Text style={s.bcBrandSub}>LIGA · MERCADO · COMUNIDAD</Text>
        </View>
        <View style={s.bcBrandAside}>
          <Text style={s.bcBrandAsideTop}>MÁS QUE UNA LIGA</Text>
          <Text style={s.bcBrandAsideBottom}>UNA COMUNIDAD</Text>
        </View>
      </View>

      <View style={s.bcIntroBlock}>
        <Text style={s.bcEyebrow}>AJPA · INICIO</Text>
        <Text style={s.bcHeading}>Este es tu mercado</Text>
        <Text style={s.bcLead}>Todo lo importante de tu club, la liga y el mercado en un solo lugar.</Text>
      </View>

      <Pressable
        onPress={() => profile?.club ? requireClub('club') : openScreen('profile')}
        style={({ pressed }) => [s.bcHeroPress, pressed && { opacity: 0.86 }]}
      >
        <ImageBackground
          source={{ uri: BG_INICIO }}
          style={s.bcHero}
          imageStyle={s.bcHeroImage}
          resizeMode="cover"
        >
          <View style={s.bcHeroShade}>
            <View style={s.bcHeroTopRow}>
              <View style={s.bcLivePill}>
                <View style={[s.bcLiveDot, { backgroundColor: snapshot.status.market_open ? C.green : C.red }]} />
                <Text style={s.bcLiveText}>{snapshot.status.market_open ? 'MERCADO ABIERTO' : 'MERCADO CERRADO'}</Text>
              </View>
              <Text style={s.bcHeroArrow}>›</Text>
            </View>

            <View style={s.bcHeroCopy}>
              <Text style={s.bcHeroKicker}>CENTRO DE MANDO</Text>
              <Text style={s.bcHeroTitle}>{profile?.club ? profile.club.toUpperCase() : 'AJPA'}</Text>
              <Text style={s.bcHeroSubtitle}>Gestioná, competí y viví la liga desde adentro.</Text>
            </View>

            <View style={s.bcHeroStats}>
              <View style={s.bcHeroStat}>
                <Text style={s.bcHeroStatLabel}>PRESUPUESTO</Text>
                <Text numberOfLines={1} style={s.bcHeroStatValue}>{money(profile?.balance)}</Text>
              </View>
              <View style={s.bcHeroStatDivider} />
              <View style={s.bcHeroStat}>
                <Text style={s.bcHeroStatLabel}>PLANTILLA</Text>
                <Text style={s.bcHeroStatValue}>{profile?.roster_count ?? roster.length} jugadores</Text>
              </View>
            </View>
          </View>
        </ImageBackground>
      </Pressable>

      <View style={s.bcRadioCard}>
        <View style={s.bcRadioIcon}><Text style={s.bcRadioIconText}>◉</Text></View>
        <View style={s.flex}>
          <Text style={s.bcRadioLabel}>RADIO PASILLO</Text>
          <Text numberOfLines={1} style={s.bcRadioText}>{snapshot.status.market_open ? 'Mercado abierto · noticias de la liga' : 'Mercado cerrado · noticias de la liga'}</Text>
        </View>
        <View style={s.bcRadioPulse} />
      </View>

      <View style={s.bcSectionHead}>
        <Text style={s.bcSectionIcon}>🏅</Text>
        <Text style={s.bcSectionTitle}>ÚLTIMOS LOGROS</Text>
      </View>

      <View style={s.bcHonoursRow}>
        <View style={s.bcHonourCard}>
          <Text style={s.bcHonourLabel}>🏆 CAMPEÓN</Text>
          <Text numberOfLines={1} style={s.bcHonourPrimary}>{latestHonours?.season_champion?.team ?? 'Sin campeón'}</Text>
          <Text numberOfLines={1} style={s.bcHonourSecondary}>{latestHonours?.season_champion ? `DT · ${latestHonours.season_champion.manager.username}` : 'Todavía no definido'}</Text>
          <Text numberOfLines={1} style={s.bcHonourMeta}>{latestHonours?.season_champion?.competition ?? 'Temporada AJPA'}</Text>
        </View>

        <View style={s.bcHonourCard}>
          <Text style={s.bcHonourLabel}>⚽ GOLEADOR</Text>
          <Text numberOfLines={1} style={s.bcHonourPrimary}>{latestHonours?.top_scorer?.player ?? 'Sin goleador'}</Text>
          <Text numberOfLines={1} style={s.bcHonourSecondary}>{latestHonours?.top_scorer ? `${latestHonours.top_scorer.goals} goles · ${latestHonours.top_scorer.team}` : 'Todavía no definido'}</Text>
          <Text numberOfLines={1} style={s.bcHonourMeta}>{latestHonours?.top_scorer ? `DT · ${latestHonours.top_scorer.manager.username}` : 'Temporada AJPA'}</Text>
        </View>

        <View style={s.bcHonourCard}>
          <Text style={s.bcHonourLabel}>🏆 COPA</Text>
          <Text numberOfLines={2} style={s.bcHonourPrimary}>{latestHonours?.cup_champion?.team ?? 'Sin campeón todavía'}</Text>
          <Text numberOfLines={1} style={s.bcHonourSecondary}>{latestHonours?.cup_champion ? `DT · ${latestHonours.cup_champion.manager.username}` : 'Aún no se jugó copa'}</Text>
          <Text numberOfLines={1} style={s.bcHonourMeta}>{latestHonours?.cup_champion?.competition ?? 'Copa AJPA'}</Text>
        </View>
      </View>

      <View style={s.bcSectionHead}>
        <Text style={s.bcSectionIcon}>⚡</Text>
        <Text style={s.bcSectionTitle}>ACCIONES RÁPIDAS</Text>
      </View>

      <View style={s.bcQuickRow}>
        <Pressable onPress={() => requireClub('publish')} style={({ pressed }) => [s.bcQuickCard, pressed && s.bcPressed]}>
          <Text style={s.bcQuickIcon}>↥</Text>
          <Text style={s.bcQuickTitle}>Publicar{`\n`}jugador</Text>
          <Text style={s.bcQuickArrow}>›</Text>
        </Pressable>
        <Pressable onPress={() => openScreen('offers')} style={({ pressed }) => [s.bcQuickCard, pressed && s.bcPressed]}>
          <Text style={s.bcQuickIcon}>⇄</Text>
          <Text style={s.bcQuickTitle}>Mis ofertas</Text>
          <Text style={s.bcQuickArrow}>›</Text>
        </Pressable>
        <Pressable onPress={() => openScreen('transferibles')} style={({ pressed }) => [s.bcQuickCard, pressed && s.bcPressed]}>
          <Text style={s.bcQuickIcon}>◎</Text>
          <Text style={s.bcQuickTitle}>Agentes{`\n`}libres</Text>
          <Text style={s.bcQuickArrow}>›</Text>
        </Pressable>
      </View>

      <Pressable onPress={() => openScreen('search')} style={({ pressed }) => [s.bcSearchBar, pressed && s.bcPressed]}>
        <Text style={s.bcSearchIcon}>⌕</Text>
        <Text style={s.bcSearchText}>Buscar jugador</Text>
        <Text style={s.bcSearchArrow}>›</Text>
      </Pressable>

      <View style={s.bcFeatureGrid}>
        <Pressable onPress={() => openScreen('market')} style={({ pressed }) => [s.bcFeatureCard, pressed && s.bcPressed]}>
          <Text style={s.bcFeatureIcon}>⇆</Text>
          <View style={s.bcFeatureCopy}>
            <Text style={s.bcFeatureKicker}>MERCADO</Text>
            <Text style={s.bcFeatureTitle}>Mercado{`\n`}de pases</Text>
          </View>
          <Text style={s.bcFeatureArrow}>›</Text>
        </Pressable>

        <Pressable onPress={() => openScreen('league')} style={({ pressed }) => [s.bcFeatureCard, pressed && s.bcPressed]}>
          <Text style={s.bcFeatureIcon}>★</Text>
          <View style={s.bcFeatureCopy}>
            <Text style={s.bcFeatureKicker}>COMPETENCIA</Text>
            <Text style={s.bcFeatureTitle}>Liga AJPA</Text>
          </View>
          <Text style={s.bcFeatureArrow}>›</Text>
        </Pressable>

        <Pressable onPress={() => void openTeams()} style={({ pressed }) => [s.bcFeatureCard, pressed && s.bcPressed]}>
          <Text style={s.bcFeatureIcon}>♜</Text>
          <View style={s.bcFeatureCopy}>
            <Text style={s.bcFeatureKicker}>COMUNIDAD</Text>
            <Text style={s.bcFeatureTitle}>Equipos{`\n`}AJPA</Text>
          </View>
          <Text style={s.bcFeatureArrow}>›</Text>
        </Pressable>

        <Pressable onPress={() => openScreen('league')} style={({ pressed }) => [s.bcFeatureCard, pressed && s.bcPressed]}>
          <Text style={s.bcFeatureIcon}>♛</Text>
          <View style={s.bcFeatureCopy}>
            <Text style={s.bcFeatureKicker}>PALMARÉS</Text>
            <Text style={s.bcFeatureTitle}>Vitrina de{`\n`}campeones</Text>
          </View>
          <Text style={s.bcFeatureArrow}>›</Text>
        </Pressable>
      </View>

      <Pressable onPress={() => openScreen('league')} style={({ pressed }) => [s.bcResultsBar, pressed && s.bcPressed]}>
        <View style={s.bcResultsIcon}><Text style={s.bcResultsIconText}>▦</Text></View>
        <View style={s.flex}>
          <Text style={s.bcResultsTitle}>RESULTADOS</Text>
          <Text style={s.bcResultsSub}>Los marcadores y la actividad de la liga</Text>
        </View>
        <Text style={s.bcResultsArrow}>›</Text>
      </Pressable>

      <View style={s.bcBottomSpacer} />
    </ScrollView>
  );`;

ui = ui.slice(0, start) + home + '\n\n' + ui.slice(end);

const styleEnd = '\n});';
const stylePos = ui.lastIndexOf(styleEnd);
if (stylePos < 0) throw new Error('AJPA Broadcaster: no encontré el cierre de StyleSheet');

const styles = String.raw`
  bcContent: { paddingTop: 12, paddingHorizontal: 14, paddingBottom: 118, backgroundColor: 'rgba(1,5,9,0.32)' },
  bcBrandRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 17, paddingHorizontal: 2 },
  bcBrandMain: { flex: 1 },
  bcBrand: { color: '#f9fcff', fontSize: 38, lineHeight: 40, fontWeight: '900', letterSpacing: 1.1 },
  bcBrandRule: { width: 58, height: 3, borderRadius: 2, backgroundColor: '#2495ff', marginTop: 2, marginBottom: 6 },
  bcBrandSub: { color: '#5eb4ff', fontSize: 9, fontWeight: '800', letterSpacing: 1.35 },
  bcBrandAside: { marginLeft: 12, paddingLeft: 12, borderLeftWidth: 1, borderLeftColor: 'rgba(108,164,211,0.32)', alignItems: 'flex-end' },
  bcBrandAsideTop: { color: '#dcecff', fontSize: 8, fontWeight: '900', letterSpacing: 1.1 },
  bcBrandAsideBottom: { color: '#6baee4', fontSize: 8, fontWeight: '800', letterSpacing: 1.05, marginTop: 3 },
  bcIntroBlock: { marginBottom: 13 },
  bcEyebrow: { color: '#4ca8ff', fontSize: 10, fontWeight: '900', letterSpacing: 1.45, marginBottom: 5 },
  bcHeading: { color: '#ffffff', fontSize: 27, lineHeight: 31, fontWeight: '900', letterSpacing: -0.45 },
  bcLead: { color: '#9ab0c4', fontSize: 12.5, lineHeight: 18, marginTop: 5, maxWidth: 330 },
  bcHeroPress: { marginBottom: 12, borderRadius: 24, shadowColor: '#168cff', shadowOpacity: 0.27, shadowRadius: 14, shadowOffset: { width: 0, height: 7 }, elevation: 10 },
  bcHero: { minHeight: 220, overflow: 'hidden', borderRadius: 24, borderWidth: 1, borderColor: 'rgba(54,151,235,0.62)' },
  bcHeroImage: { borderRadius: 24, opacity: 0.72 },
  bcHeroShade: { flex: 1, minHeight: 220, padding: 17, justifyContent: 'space-between', backgroundColor: 'rgba(1,8,15,0.48)' },
  bcHeroTopRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  bcLivePill: { flexDirection: 'row', alignItems: 'center', alignSelf: 'flex-start', paddingHorizontal: 9, paddingVertical: 6, borderRadius: 999, borderWidth: 1, borderColor: 'rgba(124,176,219,0.31)', backgroundColor: 'rgba(1,9,17,0.72)' },
  bcLiveDot: { width: 7, height: 7, borderRadius: 7, marginRight: 6 },
  bcLiveText: { color: '#e9f5ff', fontSize: 9, fontWeight: '900', letterSpacing: 1.0 },
  bcHeroArrow: { color: '#79bdff', fontSize: 34, lineHeight: 34, fontWeight: '300' },
  bcHeroCopy: { marginTop: 20, maxWidth: '83%' },
  bcHeroKicker: { color: '#63b8ff', fontSize: 9.5, fontWeight: '900', letterSpacing: 1.45, marginBottom: 4 },
  bcHeroTitle: { color: '#ffffff', fontSize: 30, lineHeight: 33, fontWeight: '900', textShadowColor: 'rgba(0,0,0,0.9)', textShadowOffset: { width: 0, height: 2 }, textShadowRadius: 7 },
  bcHeroSubtitle: { color: '#d7e7f4', fontSize: 12, lineHeight: 17, marginTop: 5, fontWeight: '600' },
  bcHeroStats: { flexDirection: 'row', alignItems: 'center', marginTop: 17, paddingTop: 12, borderTopWidth: 1, borderTopColor: 'rgba(150,196,233,0.18)' },
  bcHeroStat: { flex: 1 },
  bcHeroStatLabel: { color: '#6fa8d5', fontSize: 8, fontWeight: '900', letterSpacing: 1.15, marginBottom: 3 },
  bcHeroStatValue: { color: '#f7fbff', fontSize: 14, fontWeight: '900' },
  bcHeroStatDivider: { width: 1, height: 28, backgroundColor: 'rgba(135,184,224,0.21)', marginHorizontal: 13 },
  bcRadioCard: { minHeight: 64, flexDirection: 'row', alignItems: 'center', borderRadius: 18, borderWidth: 1, borderColor: 'rgba(36,113,170,0.54)', backgroundColor: 'rgba(4,15,25,0.88)', paddingHorizontal: 13, paddingVertical: 10, marginBottom: 20 },
  bcRadioIcon: { width: 36, height: 36, borderRadius: 12, alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(35,143,230,0.13)', borderWidth: 1, borderColor: 'rgba(52,155,236,0.42)', marginRight: 11 },
  bcRadioIconText: { color: '#51adf7', fontSize: 19, fontWeight: '900' },
  bcRadioLabel: { color: '#55b2ff', fontSize: 9, fontWeight: '900', letterSpacing: 1.3, marginBottom: 2 },
  bcRadioText: { color: '#dbe8f3', fontSize: 12, fontWeight: '700' },
  bcRadioPulse: { width: 7, height: 7, borderRadius: 8, backgroundColor: '#ef6470', marginLeft: 9, shadowColor: '#ef6470', shadowOpacity: 0.9, shadowRadius: 6 },
  bcSectionHead: { flexDirection: 'row', alignItems: 'center', marginTop: 3, marginBottom: 10 },
  bcSectionIcon: { fontSize: 13, marginRight: 7 },
  bcSectionTitle: { color: '#dcebf7', fontSize: 10.5, fontWeight: '900', letterSpacing: 1.5 },
  bcHonoursRow: { flexDirection: 'row', gap: 8, marginBottom: 21 },
  bcHonourCard: { flex: 1, minHeight: 118, borderRadius: 17, borderWidth: 1, borderColor: 'rgba(41,93,133,0.64)', backgroundColor: 'rgba(5,16,26,0.92)', padding: 10, overflow: 'hidden' },
  bcHonourLabel: { color: '#74bfff', fontSize: 8.5, fontWeight: '900', letterSpacing: 0.65, marginBottom: 12 },
  bcHonourPrimary: { color: '#ffffff', fontSize: 12.5, lineHeight: 15, fontWeight: '900', marginBottom: 5 },
  bcHonourSecondary: { color: '#aebfcd', fontSize: 9.2, lineHeight: 12, fontWeight: '700' },
  bcHonourMeta: { color: '#5f8daf', fontSize: 8.5, lineHeight: 11, marginTop: 4, fontWeight: '700' },
  bcQuickRow: { flexDirection: 'row', gap: 8, marginBottom: 8 },
  bcQuickCard: { flex: 1, minHeight: 102, borderRadius: 18, borderWidth: 1, borderColor: 'rgba(39,103,151,0.58)', backgroundColor: 'rgba(5,18,29,0.92)', padding: 11, justifyContent: 'space-between' },
  bcQuickIcon: { color: '#52affc', fontSize: 24, fontWeight: '700' },
  bcQuickTitle: { color: '#f2f8fd', fontSize: 11, lineHeight: 14, fontWeight: '800', minHeight: 29 },
  bcQuickArrow: { position: 'absolute', right: 10, top: 9, color: '#5593bf', fontSize: 21 },
  bcPressed: { opacity: 0.73, transform: [{ scale: 0.99 }] },
  bcSearchBar: { minHeight: 52, flexDirection: 'row', alignItems: 'center', borderRadius: 16, borderWidth: 1, borderColor: 'rgba(38,96,140,0.58)', backgroundColor: 'rgba(4,15,25,0.90)', paddingHorizontal: 14, marginBottom: 20 },
  bcSearchIcon: { color: '#62b7ff', fontSize: 23, marginRight: 10 },
  bcSearchText: { flex: 1, color: '#eaf4fc', fontSize: 12.5, fontWeight: '800' },
  bcSearchArrow: { color: '#568cb5', fontSize: 22 },
  bcFeatureGrid: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', marginTop: 2, marginBottom: 9 },
  bcFeatureCard: { width: '48.7%', minHeight: 142, borderRadius: 20, borderWidth: 1, borderColor: 'rgba(42,104,151,0.58)', backgroundColor: 'rgba(5,17,28,0.93)', padding: 14, marginBottom: 9, overflow: 'hidden' },
  bcFeatureIcon: { color: '#4ca9f6', fontSize: 30, fontWeight: '800', opacity: 0.88 },
  bcFeatureCopy: { flex: 1, justifyContent: 'flex-end', paddingTop: 12 },
  bcFeatureKicker: { color: '#5188b2', fontSize: 8, fontWeight: '900', letterSpacing: 1.05, marginBottom: 4 },
  bcFeatureTitle: { color: '#f6fbff', fontSize: 15, lineHeight: 18, fontWeight: '900' },
  bcFeatureArrow: { position: 'absolute', right: 12, top: 10, color: '#518ab3', fontSize: 23 },
  bcResultsBar: { minHeight: 70, flexDirection: 'row', alignItems: 'center', borderRadius: 19, borderWidth: 1, borderColor: 'rgba(42,103,149,0.58)', backgroundColor: 'rgba(5,17,28,0.95)', paddingHorizontal: 13, paddingVertical: 11 },
  bcResultsIcon: { width: 40, height: 40, borderRadius: 13, alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(38,133,207,0.13)', borderWidth: 1, borderColor: 'rgba(50,141,211,0.36)', marginRight: 11 },
  bcResultsIconText: { color: '#64b8fb', fontSize: 20, fontWeight: '900' },
  bcResultsTitle: { color: '#f1f8fe', fontSize: 12, fontWeight: '900', letterSpacing: 0.7 },
  bcResultsSub: { color: '#8199ad', fontSize: 9.5, marginTop: 3, fontWeight: '600' },
  bcResultsArrow: { color: '#548ab3', fontSize: 24 },
  bcBottomSpacer: { height: 14 },
`;

ui = ui.slice(0, stylePos) + styles + ui.slice(stylePos);
fs.writeFileSync(uiPath, ui);
console.log('AJPA Broadcaster: Inicio rediseñado aplicado.');
