import fs from 'node:fs';

function replaceBlock(source, startMarker, endMarker, replacement, label) {
  const start = source.indexOf(startMarker);
  if (start < 0) throw new Error(`AJPA unified UI: no encontré inicio de ${label}`);
  const end = source.indexOf(endMarker, start + startMarker.length);
  if (end < 0) throw new Error(`AJPA unified UI: no encontré fin de ${label}`);
  return source.slice(0, start) + replacement + '\n\n' + source.slice(end);
}

function appendOverrides(source, styleVar, rules, marker) {
  if (source.includes(marker)) return source;
  const block = `
\n// ${marker}
Object.assign(${styleVar} as any, ${JSON.stringify(rules, null, 2)});
`;
  return source + block;
}

const uiPath = new URL('../src/BotParityAppV2.tsx', import.meta.url);
let ui = fs.readFileSync(uiPath, 'utf8');

if (!ui.includes("from './AjpaIcon'")) {
  const marker = "import SeasonCountdownBanner from './SeasonCountdownBanner';";
  if (!ui.includes(marker)) throw new Error('AJPA unified UI: no encontré import SeasonCountdownBanner');
  ui = ui.replace(marker, marker + "\nimport { AjpaIcon, AjpaIconName, AjpaIconTile } from './AjpaIcon';");
}

if (!ui.includes('function iconForTitle(')) {
  const marker = 'const money = (value: number | null | undefined) =>';
  const helper = `function iconForTitle(title: string, danger = false): AjpaIconName {
  const key = title.normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').toLowerCase();
  if (danger || key.includes('claus') || key.includes('renunciar') || key.includes('quitar') || key.includes('cerrar')) return 'closed';
  if (key.includes('club') || key.includes('plantel') || key.includes('plantilla') || key.includes('asign')) return 'club';
  if (key.includes('liga') || key.includes('tabla') || key.includes('goleador') || key.includes('temporada') || key.includes('partido')) return 'league';
  if (key.includes('copa') || key.includes('champions') || key.includes('europa') || key.includes('titulo') || key.includes('palmares')) return 'cups';
  if (key.includes('perfil') || key.includes('cuenta')) return 'profile';
  if (key.includes('admin') || key.includes('staff') || key.includes('gestion') || key.includes('operacion') || key.includes('econom') || key.includes('dinero')) return 'admin';
  if (key.includes('mercado') || key.includes('transfer') || key.includes('publicar') || key.includes('oferta') || key.includes('agente') || key.includes('buscar') || key.includes('historial') || key.includes('mover')) return 'market';
  return 'more';
}

function cleanSectionTitle(title: string) {
  return title.replace(/^[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9]+/, '').trim();
}

`;
  if (!ui.includes(marker)) throw new Error('AJPA unified UI: no encontré money');
  ui = ui.replace(marker, helper + marker);
}

const menuReplacement = `function MenuTile({
  emoji,
  title,
  subtitle,
  onPress,
  danger = false,
}: {
  emoji: string;
  title: string;
  subtitle?: string;
  onPress: () => void;
  danger?: boolean;
}) {
  const icon = iconForTitle(title, danger);
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [s.menuTile, danger && s.menuDanger, pressed && s.uiPressed]}>
      <AjpaIconTile name={icon} tileSize={42} size={21} tone={danger ? '#873540' : undefined} />
      <View style={s.menuCopy}>
        <Text style={[s.menuTitle, danger && { color: C.red }]}>{title}</Text>
        {subtitle ? <Text style={s.menuSubtitle}>{subtitle}</Text> : null}
      </View>
      <Text style={[s.chevron, danger && { color: C.red }]}>›</Text>
    </Pressable>
  );
}`;
ui = replaceBlock(ui, 'function MenuTile({', 'function SectionLabel(', menuReplacement, 'MenuTile');

const sectionReplacement = `function SectionLabel({ title, badge }: { title: string; badge?: string }) {
  return (
    <View style={s.sectionLabelRow}>
      <Text style={s.sectionLabel}>{cleanSectionTitle(title)}</Text>
      {badge ? <Text style={s.sectionBadge}>{badge}</Text> : null}
    </View>
  );
}`;
ui = replaceBlock(ui, 'function SectionLabel({', 'function FeatureTile({', sectionReplacement, 'SectionLabel');

const featureReplacement = `function FeatureTile({
  emoji,
  title,
  subtitle,
  onPress,
  danger = false,
}: {
  emoji: string;
  title: string;
  subtitle?: string;
  onPress: () => void;
  danger?: boolean;
}) {
  const icon = iconForTitle(title, danger);
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [s.featureTile, danger && s.featureTileDanger, pressed && s.uiPressed]}>
      <AjpaIconTile name={icon} tileSize={46} size={23} tone={danger ? '#873540' : undefined} />
      <View style={s.featureTextWrap}>
        <Text style={[s.featureTitle, danger && { color: C.red }]} numberOfLines={2}>{title}</Text>
        {subtitle ? <Text style={s.featureSubtitle} numberOfLines={3}>{subtitle}</Text> : null}
      </View>
      <Text style={[s.featureArrowText, danger && { color: C.red }]}>›</Text>
    </Pressable>
  );
}`;
ui = replaceBlock(ui, 'function FeatureTile({', 'function QuickAction({', featureReplacement, 'FeatureTile');

const quickReplacement = `function QuickAction({
  emoji,
  title,
  onPress,
  danger = false,
}: {
  emoji: string;
  title: string;
  onPress: () => void;
  danger?: boolean;
}) {
  const icon = iconForTitle(title, danger);
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [s.quickAction, danger && s.quickActionDanger, pressed && s.uiPressed]}>
      <AjpaIcon name={icon} size={18} color={danger ? C.red : C.blueSoft} />
      <Text style={[s.quickTitle, danger && { color: C.red }]} numberOfLines={2}>{title}</Text>
      <Text style={[s.quickChevron, danger && { color: C.red }]}>›</Text>
    </Pressable>
  );
}`;
ui = replaceBlock(ui, 'function QuickAction({', 'function Title(', quickReplacement, 'QuickAction');

const sourceOld = "source={typeof screenBackground === 'string' ? { uri: screenBackground } : screenBackground}";
if (ui.includes(sourceOld)) {
  ui = ui.replace(sourceOld, "source={embedded ? undefined : (typeof screenBackground === 'string' ? { uri: screenBackground } : screenBackground)}");
}
ui = ui.replace(
  "style={s.screenBackground}",
  "style={[s.screenBackground, embedded && s.embeddedScreen]}",
);

const uiRules = {
  root: { flex: 1, backgroundColor: '#07131F' },
  main: { flex: 1, backgroundColor: '#07131F' },
  screenBackground: { flex: 1, backgroundColor: '#07131F' },
  embeddedScreen: { backgroundColor: '#07131F' },
  screenShade: { flex: 1, backgroundColor: 'rgba(7,19,31,0.96)' },
  content: { paddingHorizontal: 14, paddingTop: 14, paddingBottom: 112, gap: 10 },
  topBar: { height: 58, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 14, borderBottomWidth: 1, borderBottomColor: '#1E4058', backgroundColor: '#07131F' },
  topAction: { minHeight: 36, paddingHorizontal: 10, borderRadius: 11, borderWidth: 1, borderColor: '#244D68', backgroundColor: '#0B2233', alignItems: 'center', justifyContent: 'center' },
  topActionText: { color: '#76C7FF', fontSize: 9, fontWeight: '900', letterSpacing: 0.6 },
  profileButton: { minWidth: 82, height: 36, paddingHorizontal: 10, borderRadius: 11, borderWidth: 1, borderColor: '#244D68', alignItems: 'center', justifyContent: 'center', backgroundColor: '#0B2233' },
  profileButtonText: { color: '#DDEAF2', fontSize: 9, fontWeight: '900', letterSpacing: 0.5 },
  eyebrow: { color: '#52B6F7', fontSize: 8, fontWeight: '900', letterSpacing: 1.5, marginBottom: 4 },
  screenTitle: { color: '#F5FAFE', fontSize: 23, lineHeight: 27, fontWeight: '900' },
  muted: { color: '#91A6B6', fontSize: 11, lineHeight: 16, marginTop: 3 },
  sectionLabelRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 8, marginBottom: 2 },
  sectionLabel: { color: '#6CC5FF', fontSize: 8.5, fontWeight: '900', letterSpacing: 1.4 },
  sectionBadge: { color: '#8ED1FF', fontSize: 7, fontWeight: '900', letterSpacing: 0.8, borderWidth: 1, borderColor: '#295A79', borderRadius: 10, paddingHorizontal: 8, paddingVertical: 4, backgroundColor: '#0B2233' },
  featureGrid: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', gap: 10 },
  featureTile: { width: '48.4%', minHeight: 142, borderRadius: 17, borderWidth: 1, borderColor: '#244B66', backgroundColor: '#0B2233', padding: 12, overflow: 'hidden' },
  featureTileDanger: { borderColor: '#71313B', backgroundColor: '#25131A' },
  featureTextWrap: { flex: 1, marginTop: 10 },
  featureTitle: { color: '#F5FAFE', fontSize: 15.5, lineHeight: 18.5, fontWeight: '900' },
  featureSubtitle: { color: '#93A8B8', fontSize: 9.5, lineHeight: 13.5, marginTop: 5 },
  featureArrowText: { position: 'absolute', right: 11, top: 13, color: '#32A8F7', fontSize: 22, lineHeight: 22, fontWeight: '900' },
  quickGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  quickAction: { flexGrow: 1, flexBasis: '30%', minWidth: 96, minHeight: 58, flexDirection: 'row', alignItems: 'center', borderRadius: 14, borderWidth: 1, borderColor: '#244B66', backgroundColor: '#0B2233', paddingHorizontal: 10, paddingVertical: 9, gap: 7 },
  quickActionDanger: { borderColor: '#71313B', backgroundColor: '#25131A' },
  quickTitle: { flex: 1, color: '#EAF3F8', fontSize: 9.5, lineHeight: 12, fontWeight: '800' },
  quickChevron: { color: '#32A8F7', fontSize: 17, fontWeight: '900' },
  menuTile: { minHeight: 72, flexDirection: 'row', alignItems: 'center', backgroundColor: '#0B2233', borderWidth: 1, borderColor: '#244B66', borderRadius: 16, paddingHorizontal: 12, paddingVertical: 10, gap: 10 },
  menuCopy: { flex: 1, minWidth: 0 },
  menuDanger: { borderColor: '#71313B', backgroundColor: '#25131A' },
  menuTitle: { color: '#F5FAFE', fontSize: 14, fontWeight: '900' },
  menuSubtitle: { color: '#91A6B6', fontSize: 9.5, lineHeight: 13.5, marginTop: 2 },
  chevron: { color: '#32A8F7', fontSize: 22, marginLeft: 4 },
  heroClubCard: { minHeight: 126, flexDirection: 'row', alignItems: 'center', borderRadius: 18, borderWidth: 1, borderColor: '#285A78', backgroundColor: '#0B2233', padding: 14, overflow: 'hidden' },
  wideTile: { minHeight: 84, flexDirection: 'row', alignItems: 'center', borderRadius: 16, borderWidth: 1, borderColor: '#244B66', backgroundColor: '#0B2233', padding: 12, overflow: 'hidden' },
  card: { backgroundColor: '#0B2233', borderWidth: 1, borderColor: '#244B66', borderRadius: 16, padding: 13 },
  statCard: { backgroundColor: '#0B2233', borderWidth: 1, borderColor: '#244B66', borderRadius: 16, padding: 14 },
  summaryCard: { flex: 1, backgroundColor: '#0B2233', borderWidth: 1, borderColor: '#244B66', borderRadius: 14, padding: 12 },
  editorCard: { backgroundColor: '#0B2233', borderWidth: 1, borderColor: '#2B6E97', borderRadius: 16, padding: 13 },
  input: { minHeight: 46, backgroundColor: '#081925', borderWidth: 1, borderColor: '#294B61', borderRadius: 12, paddingHorizontal: 12, color: '#F5FAFE', fontSize: 15 },
  button: { minHeight: 44, borderRadius: 12, paddingHorizontal: 13, alignItems: 'center', justifyContent: 'center', backgroundColor: '#228DE0' },
  buttonGreen: { backgroundColor: '#168553' },
  buttonRed: { backgroundColor: '#8A3541' },
  buttonGhost: { backgroundColor: '#102A3D', borderWidth: 1, borderColor: '#31536B' },
  homeStatusCard: { flex: 1, minHeight: 68, borderRadius: 15, borderWidth: 1, borderColor: '#244B66', backgroundColor: '#0B2233', padding: 12, justifyContent: 'center' },
  marketControlCard: { flexDirection: 'row', alignItems: 'center', gap: 10, borderRadius: 16, borderWidth: 1, padding: 13, backgroundColor: '#0B2233', borderColor: '#244B66' },
  budgetCard: { flexDirection: 'row', alignItems: 'center', gap: 10, borderRadius: 15, borderWidth: 1, borderColor: '#244B66', backgroundColor: '#0B2233', padding: 12 },
  tableRow: { flexDirection: 'row', alignItems: 'center', minHeight: 46, borderRadius: 12, borderWidth: 1, borderColor: '#1E4058', backgroundColor: '#0A1D2B', paddingHorizontal: 10, paddingVertical: 8 },
  uiPressed: { opacity: 0.72, transform: [{ scale: 0.992 }] }
};
ui = appendOverrides(ui, 's', uiRules, 'AJPA_UNIFIED_UI_V1');
fs.writeFileSync(uiPath, ui);

const trophyPath = new URL('../src/TrophyCabinetFab.tsx', import.meta.url);
let trophy = fs.readFileSync(trophyPath, 'utf8');
const trophyRules = {
  screen: { flex: 1, backgroundColor: '#07131F' },
  topBar: { minHeight: 62, flexDirection: 'row', alignItems: 'center', borderBottomWidth: 1, borderBottomColor: '#1E4058', backgroundColor: '#07131F', paddingHorizontal: 14 },
  backButton: { width: 38, height: 38, borderRadius: 11, borderWidth: 1, borderColor: '#244D68', backgroundColor: '#0B2233', alignItems: 'center', justifyContent: 'center' },
  scroll: { flex: 1, backgroundColor: '#07131F' },
  content: { padding: 14, paddingBottom: 110, gap: 11 },
  trophyCard: { borderRadius: 18, borderWidth: 1, borderColor: '#244B66', backgroundColor: '#0B2233', overflow: 'hidden' },
  trophyStage: { minHeight: 150, backgroundColor: '#081925', alignItems: 'center', justifyContent: 'center', padding: 12 },
  trophyCopy: { padding: 13 },
  historyPanel: { borderRadius: 18, borderWidth: 1, borderColor: '#244B66', backgroundColor: '#0B2233', padding: 13 },
  winnerRow: { flexDirection: 'row', alignItems: 'center', borderRadius: 13, borderWidth: 1, borderColor: '#1E4058', backgroundColor: '#0A1D2B', padding: 10, marginTop: 7 },
  rankingPanel: { borderRadius: 18, borderWidth: 1, borderColor: '#244B66', backgroundColor: '#0B2233', padding: 13 },
  rankingTab: { flex: 1, minHeight: 38, borderRadius: 11, alignItems: 'center', justifyContent: 'center', backgroundColor: '#081925', borderWidth: 1, borderColor: '#1E4058' },
  rankingTabActive: { backgroundColor: '#12344A', borderColor: '#2B78A8' },
  podiumCard: { flex: 1, minWidth: 0, borderRadius: 15, borderWidth: 1, borderColor: '#244B66', backgroundColor: '#0A1D2B', padding: 10, alignItems: 'center' },
  rankRow: { flexDirection: 'row', alignItems: 'center', borderRadius: 13, borderWidth: 1, borderColor: '#1E4058', backgroundColor: '#0A1D2B', padding: 10, marginTop: 7 }
};
trophy = appendOverrides(trophy, 'styles', trophyRules, 'AJPA_UNIFIED_TROPHIES_V1');
fs.writeFileSync(trophyPath, trophy);

const historyPath = new URL('../src/SeasonHistoryFab.tsx', import.meta.url);
let history = fs.readFileSync(historyPath, 'utf8');
const historyRules = {
  fab: { position: 'absolute', right: 14, bottom: 96, minHeight: 42, borderRadius: 13, borderWidth: 1, borderColor: '#2B6E97', backgroundColor: '#0B2233', paddingHorizontal: 12, alignItems: 'center', justifyContent: 'center', zIndex: 40 },
  backdrop: { flex: 1, backgroundColor: 'rgba(2,8,14,0.82)', padding: 12, justifyContent: 'center' },
  card: { maxHeight: '88%', borderRadius: 20, borderWidth: 1, borderColor: '#285A78', backgroundColor: '#07131F', padding: 14, overflow: 'hidden' },
  seasonChip: { minWidth: 104, borderRadius: 12, borderWidth: 1, borderColor: '#244B66', backgroundColor: '#0B2233', paddingHorizontal: 10, paddingVertical: 8 },
  seasonChipActive: { borderColor: '#2B78A8', backgroundColor: '#12344A' },
  sectionButton: { flex: 1, minHeight: 38, borderRadius: 11, borderWidth: 1, borderColor: '#244B66', alignItems: 'center', justifyContent: 'center', backgroundColor: '#0B2233' },
  sectionButtonActive: { backgroundColor: '#12344A', borderColor: '#2B78A8' },
  tableRow: { flexDirection: 'row', alignItems: 'center', gap: 9, borderRadius: 12, padding: 10, borderWidth: 1, borderColor: '#1E4058', backgroundColor: '#0A1D2B' },
  matchCard: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8, borderRadius: 12, padding: 12, borderWidth: 1, borderColor: '#1E4058', backgroundColor: '#0A1D2B' }
};
history = appendOverrides(history, 'styles', historyRules, 'AJPA_UNIFIED_HISTORY_V1');
fs.writeFileSync(historyPath, history);

const adminPath = new URL('../src/CompetitionCycleAdminFab.tsx', import.meta.url);
let admin = fs.readFileSync(adminPath, 'utf8');
const adminRules = {
  fab: { position: 'absolute', right: 14, bottom: 96, minHeight: 42, borderRadius: 13, borderWidth: 1, borderColor: '#2B6E97', backgroundColor: '#0B2233', paddingHorizontal: 12, alignItems: 'center', justifyContent: 'center', zIndex: 45 },
  backdrop: { flex: 1, backgroundColor: 'rgba(2,8,14,0.82)', padding: 12, justifyContent: 'center' },
  card: { maxHeight: '90%', borderRadius: 20, borderWidth: 1, borderColor: '#285A78', backgroundColor: '#07131F', padding: 14, overflow: 'hidden' },
  statusCard: { flex: 1, minWidth: 0, borderRadius: 14, borderWidth: 1, borderColor: '#244B66', backgroundColor: '#0B2233', padding: 11 },
  currentBox: { borderRadius: 15, borderWidth: 1, borderColor: '#244B66', backgroundColor: '#0B2233', padding: 12 },
  masterButton: { flex: 1, minHeight: 82, borderRadius: 16, borderWidth: 1, borderColor: '#2B6E97', backgroundColor: '#0B2233', padding: 12, justifyContent: 'center' },
  gesButton: { minHeight: 58, borderRadius: 14, borderWidth: 1, borderColor: '#2B6E97', backgroundColor: '#0B2233', padding: 11, justifyContent: 'center' },
  secondaryButton: { minHeight: 46, borderRadius: 12, borderWidth: 1, borderColor: '#244B66', backgroundColor: '#102A3D', alignItems: 'center', justifyContent: 'center', paddingHorizontal: 12 },
  configBox: { borderRadius: 16, borderWidth: 1, borderColor: '#244B66', backgroundColor: '#0B2233', padding: 12 },
  input: { minHeight: 46, borderRadius: 12, borderWidth: 1, borderColor: '#294B61', backgroundColor: '#081925', color: '#F5FAFE', paddingHorizontal: 12 },
  nextBox: { borderRadius: 16, borderWidth: 1, borderColor: '#244B66', backgroundColor: '#0B2233', padding: 12 }
};
admin = appendOverrides(admin, 'styles', adminRules, 'AJPA_UNIFIED_ADMIN_V1');
fs.writeFileSync(adminPath, admin);

const matchPath = new URL('../src/MatchSearchShell.tsx', import.meta.url);
let match = fs.readFileSync(matchPath, 'utf8');
const matchRules = {
  root: { flex: 1, backgroundColor: '#07131F' },
  overlay: { position: 'absolute', top: 0, right: 0, bottom: 0, left: 0, backgroundColor: '#07131F', zIndex: 50 },
  header: { minHeight: 62, paddingHorizontal: 14, borderBottomWidth: 1, borderBottomColor: '#1E4058', backgroundColor: '#07131F', flexDirection: 'row', alignItems: 'center', gap: 10 },
  content: { padding: 14, paddingBottom: 110, gap: 10 },
  clubStrip: { borderWidth: 1, borderColor: '#244B66', backgroundColor: '#0B2233', borderRadius: 15, padding: 12 },
  notice: { backgroundColor: '#0B2233', borderWidth: 1, borderColor: '#244B66', borderRadius: 15, padding: 12 },
  formCard: { backgroundColor: '#0B2233', borderWidth: 1, borderColor: '#2B6E97', borderRadius: 16, padding: 13 },
  searchCard: { backgroundColor: '#0B2233', borderWidth: 1, borderColor: '#244B66', borderRadius: 16, padding: 13 },
  input: { minHeight: 46, borderRadius: 12, borderWidth: 1, borderColor: '#294B61', backgroundColor: '#081925', color: '#F5FAFE', paddingHorizontal: 12, fontSize: 15 }
};
match = appendOverrides(match, 's', matchRules, 'AJPA_UNIFIED_MATCH_V1');
fs.writeFileSync(matchPath, match);

console.log('AJPA UI Lab: todas las pantallas funcionales usan la estética visual unificada.');
