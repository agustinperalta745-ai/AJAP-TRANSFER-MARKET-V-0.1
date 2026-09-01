import fs from 'node:fs';

const uiPath = 'src/BotParityAppV2.tsx';
let ui = fs.readFileSync(uiPath, 'utf8');

if (!ui.includes("import { ClubBadge } from './teamBadges';")) {
  const anchor = "import { BG_PERFIL } from './bg_perfil';";
  if (!ui.includes(anchor)) throw new Error('Monaco badge test: no encontré el import de BG_PERFIL');
  ui = ui.replace(anchor, `${anchor}\nimport { ClubBadge } from './teamBadges';`);
}

const oldHero = '<View style={s.heroIconWrap}><Text style={s.heroIcon}>🛡️</Text></View>';
const newHero = '<View style={s.heroIconWrap}><ClubBadge club={club} size={62} /></View>';

if (!ui.includes(newHero)) {
  if (!ui.includes(oldHero)) throw new Error('Monaco badge test: no encontré el escudo genérico de HeroClubCard');
  ui = ui.replace(oldHero, newHero);
}

fs.writeFileSync(uiPath, ui);
console.log('Monaco badge test aplicado: HeroClubCard usa PNG saneado solo para AS Monaco.');
