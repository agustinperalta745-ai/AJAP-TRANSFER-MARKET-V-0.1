import fs from 'node:fs';

const uiPath = 'src/BotParityAppV2.tsx';
let ui = fs.readFileSync(uiPath, 'utf8');

const badgeImport = "import { ClubBadge, ClubMatchup, getClubTheme } from './teamBadges';";
if (!ui.includes(badgeImport)) {
  const variants = [
    "import { ClubBadge, ClubMatchup } from './teamBadges';",
    "import { ClubBadge, getClubTheme } from './teamBadges';",
    "import { ClubBadge } from './teamBadges';",
  ];
  const found = variants.find((candidate) => ui.includes(candidate));
  if (found) {
    ui = ui.replace(found, badgeImport);
  } else {
    const anchor = "import { BG_PERFIL } from './bg_perfil';";
    if (!ui.includes(anchor)) throw new Error('Club identity: no encontré el bloque de imports');
    ui = ui.replace(anchor, `${anchor}\n${badgeImport}`);
  }
}

const heroStart = ui.indexOf('function HeroClubCard({');
const wideStart = ui.indexOf('function WideTile({', heroStart);
if (heroStart < 0 || wideStart < 0) throw new Error('Club identity: no encontré HeroClubCard');

const hero = String.raw`function HeroClubCard({
  club,
  budget,
  players,
  marketOpen,
  onPress,
}: {
  club: string;
  budget: string;
  players: number;
  marketOpen: boolean;
  onPress: () => void;
}) {
  const theme = getClubTheme(club);
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [s.clubHeroCard, pressed && { opacity: 0.80, transform: [{ scale: 0.994 }] }]}>
      <View style={[s.clubHeroSurface, { borderColor: theme.accent }]}>
        <View pointerEvents="none" style={[s.clubHeroGlowEdge, { backgroundColor: theme.primary }]} />
        <View pointerEvents="none" style={[s.clubColorWash, { backgroundColor: theme.primary }]} />
        <View pointerEvents="none" style={[s.clubColorFadeA, { backgroundColor: theme.primary }]} />
        <View pointerEvents="none" style={[s.clubColorFadeB, { backgroundColor: theme.secondary }]} />
        <View pointerEvents="none" style={s.clubHeroWatermark}>
          <ClubBadge club={club} size={190} style={s.clubHeroWatermarkBadge} />
        </View>

        <View style={[s.clubBadgeFrame, { borderColor: theme.accent, backgroundColor: theme.soft }]}>
          <ClubBadge club={club} size={72} />
        </View>

        <View style={s.clubHeroBody}>
          <Text style={s.heroClubName} numberOfLines={1}>{club}</Text>
          <View style={s.heroStatsRow}>
            <View style={s.heroStat}>
              <Text style={s.heroStatLabel}>PRESUPUESTO</Text>
              <Text style={s.heroStatValue} numberOfLines={1}>{budget}</Text>
            </View>
            <View style={[s.heroDivider, { backgroundColor: theme.soft }]} />
            <View style={s.heroStat}>
              <Text style={s.heroStatLabel}>PLANTILLA</Text>
              <Text style={s.heroStatValue} numberOfLines={1}>{players} jugadores</Text>
            </View>
          </View>
          <View style={s.heroStatusRow}>
            <View style={[s.heroStatusDot, { backgroundColor: marketOpen ? C.green : C.red }]} />
            <Text style={[s.heroStatusText, { color: marketOpen ? C.green : C.red }]}>{marketOpen ? 'Mercado abierto' : 'Mercado cerrado'}</Text>
          </View>
        </View>

        <View style={[s.wideArrow, { borderColor: theme.accent, backgroundColor: 'rgba(2,13,23,0.54)' }]}>
          <Text style={[s.wideArrowText, { color: theme.accent }]}>›</Text>
        </View>
      </View>
    </Pressable>
  );
}

`;
ui = ui.slice(0, heroStart) + hero + ui.slice(wideStart);

const styleClose = '\n});';
const stylePos = ui.lastIndexOf(styleClose);
if (stylePos < 0) throw new Error('Club identity: no encontré cierre de estilos');

const extraStyles = String.raw`
  clubHeroCard: { borderRadius: 27, marginBottom: 2, shadowColor: '#000000', shadowOpacity: 0.42, shadowRadius: 15, shadowOffset: { width: 0, height: 8 }, elevation: 11 },
  clubHeroSurface: { minHeight: 160, flexDirection: 'row', alignItems: 'center', borderRadius: 27, borderWidth: 1.35, backgroundColor: 'rgba(3,15,26,0.95)', paddingVertical: 17, paddingHorizontal: 16, overflow: 'hidden' },
  clubHeroGlowEdge: { position: 'absolute', left: 0, top: 17, bottom: 17, width: 3, borderRadius: 3, opacity: 0.92 },
  clubColorWash: { position: 'absolute', left: -72, top: -68, width: '62%', height: 300, borderRadius: 180, opacity: 0.44 },
  clubColorFadeA: { position: 'absolute', left: '15%', top: -52, width: '48%', height: 270, borderRadius: 160, opacity: 0.23 },
  clubColorFadeB: { position: 'absolute', left: '36%', top: -52, width: '44%', height: 270, borderRadius: 160, opacity: 0.10 },
  clubHeroWatermark: { position: 'absolute', right: -34, top: -18, width: 205, height: 205, alignItems: 'center', justifyContent: 'center', opacity: 0.10, transform: [{ rotate: '-7deg' }] },
  clubHeroWatermarkBadge: { opacity: 0.96 },
  clubBadgeFrame: { width: 88, height: 88, borderRadius: 28, borderWidth: 1.4, alignItems: 'center', justifyContent: 'center', marginRight: 15, shadowColor: '#000000', shadowOpacity: 0.25, shadowRadius: 8, shadowOffset: { width: 0, height: 4 }, elevation: 4 },
  clubHeroBody: { flex: 1, minWidth: 0, zIndex: 2 },
`;

ui = ui.slice(0, stylePos) + extraStyles + ui.slice(stylePos);
fs.writeFileSync(uiPath, ui);
console.log('AJPA club identity: escudo + estela de color + watermark aplicados a Mi Club.');
