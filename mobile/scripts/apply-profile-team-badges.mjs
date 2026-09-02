import fs from 'node:fs';

const uiPath = new URL('../src/BotParityAppV2.tsx', import.meta.url);
let ui = fs.readFileSync(uiPath, 'utf8');

function replaceBadgeForContext(contextExpr, badgeExpr, label) {
  const pattern = new RegExp(
    String.raw`(<View style=\{s\.heroIconWrap\}>\s*(?:<IconSurfaceDepth \/>\s*)?)<Text style=\{s\.heroIcon\}>🛡️<\/Text>(\s*<\/View>\s*<View style=\{s\.flex\}>\s*<Text style=\{s\.[^}]+\}>\{${contextExpr}\}<\/Text>)`,
  );
  const replacement = `$1<ClubBadge club={${badgeExpr}} size={62} />$2`;
  if (pattern.test(ui)) ui = ui.replace(pattern, replacement);
  if (!ui.includes(`<ClubBadge club={${badgeExpr}} size={62} />`)) {
    throw new Error(`AJPA profile badges patch: no se pudo aplicar el escudo real en ${label}`);
  }
}

replaceBadgeForContext('club\\.club', 'club.club', 'la lista de equipos');
replaceBadgeForContext('selectedClubProfile\\.club', 'selectedClubProfile.club', 'el perfil público');

if (!ui.includes(`import { ClubBadge`)) {
  throw new Error('AJPA profile badges patch: ClubBadge no está importado; revisar orden de transforms');
}

fs.writeFileSync(uiPath, ui);
console.log('AJPA profile badges: lista de equipos + perfil público usan escudos reales.');
