import fs from 'node:fs';

const REQUIRED_BADGES = [
  'ajax','as_monaco','aston_villa','atletico_madrid','benfica','bolton_wanderers','everton','feyenoord','fiorentina','fulham','galatasaray','lazio','manchester_city','middlesbrough','olympique_lyon','olympique_marseille','porto','psg','real_betis','sevilla','torino','tottenham_hotspur','villarreal','west_ham_united','zaragoza',
];
for (const badge of REQUIRED_BADGES) {
  const badgePath = `assets/teams/${badge}.png`;
  if (!fs.existsSync(badgePath)) throw new Error(`Team badges patch: falta ${badgePath}`);
}

function replaceOnce(text, from, to, label) {
  if (text.includes(to)) return text;
  if (!text.includes(from)) throw new Error(`Team badges patch: no se encontró ${label}`);
  return text.replace(from, to);
}

function patchBotParity() {
  const path = 'src/BotParityAppV2.tsx';
  let ui = fs.readFileSync(path, 'utf8');

  ui = replaceOnce(
    ui,
    "import { BG_PERFIL } from './bg_perfil';",
    "import { BG_PERFIL } from './bg_perfil';\nimport { ClubBadge, ClubMatchup } from './teamBadges';",
    'import BotParityAppV2',
  );

  ui = replaceOnce(
    ui,
    "          <Text style={s.playerValue}>Valor AJPA {money(player.market_value)}</Text>\n        </View>\n      </View>",
    "          <Text style={s.playerValue}>Valor AJPA {money(player.market_value)}</Text>\n        </View>\n        <ClubBadge club={player.club} size={50} />\n      </View>",
    'escudo PlayerCard',
  );

  ui = replaceOnce(
    ui,
    "          <Text style={s.playerValue}>{item.operation_type}</Text>\n        </View>\n        <Text style={[s.price, item.is_free_agent && { color: C.green }]}>{item.price}</Text>",
    "          <Text style={s.playerValue}>{item.operation_type}</Text>\n        </View>\n        <ClubBadge club={item.club} size={48} />\n        <Text style={[s.price, item.is_free_agent && { color: C.green }]}>{item.price}</Text>",
    'escudo MarketCard',
  );

  ui = replaceOnce(
    ui,
    "      <Text style={s.muted}>{offer.from_club} → {offer.to_club}</Text>\n      <Text style={s.playerValue}>Propuesta: {offer.amount || '$0'} · {offer.operation_type}</Text>",
    "      <Text style={s.muted}>{offer.from_club} → {offer.to_club}</Text>\n      <ClubMatchup home={offer.from_club} away={offer.to_club} size={34} />\n      <Text style={s.playerValue}>Propuesta: {offer.amount || '$0'} · {offer.operation_type}</Text>",
    'escudos OfferCard',
  );

  ui = replaceOnce(
    ui,
    `    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl}>
      <Title
        eyebrow="AJPA TRANSFER MARKET"
        title={profile?.club ? profile.club.toUpperCase() : profile?.is_staff ? 'PANEL STAFF' : 'MENÚ PRINCIPAL'}
        subtitle="La misma jerarquía que el panel /mercado de Discord."
      />`,
    `    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl}>
      <View style={s.homeHeroRow}>
        <View style={s.homeHeroText}>
          <Title
            eyebrow="AJPA TRANSFER MARKET"
            title={profile?.club ? profile.club.toUpperCase() : profile?.is_staff ? 'PANEL STAFF' : 'MENÚ PRINCIPAL'}
            subtitle="La misma jerarquía que el panel /mercado de Discord."
          />
        </View>
        {profile?.club ? <View style={s.homeHeroBadgeWrap}><ClubBadge club={profile.club} size={154} /></View> : null}
      </View>`,
    'escudo home protagonista',
  );

  ui = replaceOnce(
    ui,
    "    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl}>\n      <Title eyebrow=\"MI CLUB\" title={profile?.club ?? 'Mi Club'} subtitle=\"Mismas opciones que el submenú del bot.\" />",
    "    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl}>\n      <View style={s.clubHeader}><ClubBadge club={profile?.club} size={96} /><View style={s.flex}><Title eyebrow=\"MI CLUB\" title={profile?.club ?? 'Mi Club'} subtitle=\"Mismas opciones que el submenú del bot.\" /></View></View>",
    'escudo Mi Club',
  );

  ui = replaceOnce(
    ui,
    `            <View style={s.ovrBox}><Text style={s.ovrValue}>{index + 1}</Text><Text style={s.ovrLabel}>POS</Text></View>
            <View style={s.flex}>`,
    `            <View style={s.ovrBox}><Text style={s.ovrValue}>{index + 1}</Text><Text style={s.ovrLabel}>POS</Text></View>
            <ClubBadge club={row.team} size={46} />
            <View style={[s.flex, { marginLeft: 10 }]}>`,
    'escudos tabla de liga',
  );

  ui = replaceOnce(
    ui,
    `        <View style={s.card} key={row.player + '-' + row.team}>
          <Text style={s.playerName}>{index + 1}. {row.player}</Text>
          <Text style={s.muted}>{row.team || 'Sin club'}</Text>
          <Text style={s.playerValue}>⚽ {row.goals} goles</Text>
        </View>`,
    `        <View style={s.card} key={row.player + '-' + row.team}>
          <View style={s.playerRow}>
            <ClubBadge club={row.team} size={44} />
            <View style={[s.flex, { marginLeft: 10 }]}>
              <Text style={s.playerName}>{index + 1}. {row.player}</Text>
              <Text style={s.muted}>{row.team || 'Sin club'}</Text>
              <Text style={s.playerValue}>⚽ {row.goals} goles</Text>
            </View>
          </View>
        </View>`,
    'escudos goleadores',
  );

  ui = replaceOnce(
    ui,
    `          <Text style={s.muted}>{item.seller || '—'} → {item.buyer || '—'}</Text>
          <Text style={s.playerValue}>{item.operation_type} · {item.amount}</Text>`,
    `          <Text style={s.muted}>{item.seller || '—'} → {item.buyer || '—'}</Text>
          <ClubMatchup home={item.seller} away={item.buyer} size={34} />
          <Text style={s.playerValue}>{item.operation_type} · {item.amount}</Text>`,
    'escudos historial',
  );

  ui = replaceOnce(
    ui,
    `        <View style={s.card} key={club.name}>
          <Text style={s.playerName}>{club.name}</Text>
          <Text style={s.playerValue}>{money(club.balance)}</Text>
          <Text style={s.muted}>{club.roster_count} jugadores</Text>
        </View>`,
    `        <View style={s.card} key={club.name}>
          <View style={s.playerRow}>
            <ClubBadge club={club.name} size={48} />
            <View style={[s.flex, { marginLeft: 10 }]}>
              <Text style={s.playerName}>{club.name}</Text>
              <Text style={s.playerValue}>{money(club.balance)}</Text>
              <Text style={s.muted}>{club.roster_count} jugadores</Text>
            </View>
          </View>
        </View>`,
    'escudos presupuestos Staff',
  );

  ui = replaceOnce(
    ui,
    `        <View style={s.card} key={item.user_id}>
          <Text style={s.playerName}>{item.club}</Text>
          <Text style={s.muted}>Discord ID: {item.user_id}</Text>
        </View>`,
    `        <View style={s.card} key={item.user_id}>
          <View style={s.playerRow}>
            <ClubBadge club={item.club} size={48} />
            <View style={[s.flex, { marginLeft: 10 }]}>
              <Text style={s.playerName}>{item.club}</Text>
              <Text style={s.muted}>Discord ID: {item.user_id}</Text>
            </View>
          </View>
        </View>`,
    'escudos asignaciones',
  );

  ui = replaceOnce(
    ui,
    "  summaryRow: { flexDirection: 'row', gap: 10 },",
    "  homeHeroRow: { minHeight: 178, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 },\n  homeHeroText: { flex: 1, minWidth: 0, justifyContent: 'center' },\n  homeHeroBadgeWrap: { width: 160, height: 168, alignItems: 'center', justifyContent: 'center' },\n  clubHeader: { flexDirection: 'row', alignItems: 'center', gap: 16, marginBottom: 8 },\n  summaryRow: { flexDirection: 'row', gap: 10 },",
    'styles BotParityAppV2',
  );

  fs.writeFileSync(path, ui);
}

function patchMatchSearch() {
  const path = 'src/MatchSearchShell.tsx';
  let ui = fs.readFileSync(path, 'utf8');

  ui = replaceOnce(
    ui,
    "import { apiRequest } from './api';",
    "import { apiRequest } from './api';\nimport { ClubBadge, ClubMatchup } from './teamBadges';",
    'import MatchSearchShell',
  );

  ui = replaceOnce(
    ui,
    "              <View style={s.clubStrip}>\n                <Text style={s.clubStripLabel}>TU CLUB</Text>\n                <Text style={s.clubStripValue}>{viewerClub}</Text>\n              </View>",
    "              <View style={s.clubStrip}>\n                <ClubBadge club={viewerClub} size={56} />\n                <View style={{ flex: 1 }}>\n                  <Text style={s.clubStripLabel}>TU CLUB</Text>\n                  <Text style={s.clubStripValue}>{viewerClub}</Text>\n                </View>\n              </View>",
    'escudo viewer club',
  );

  ui = replaceOnce(
    ui,
    "                <View style={s.cardHeader}>\n                  <View style={{ flex: 1 }}>",
    "                <View style={s.cardHeader}>\n                  <ClubBadge club={item.creator_club} size={58} />\n                  <View style={{ flex: 1 }}>",
    'escudo búsqueda',
  );

  ui = replaceOnce(
    ui,
    "                  <Text style={s.matchup}>{item.creator_club} vs {item.opponent_club}</Text>",
    "                  <View>\n                    <Text style={s.matchup}>{item.creator_club} vs {item.opponent_club}</Text>\n                    <ClubMatchup home={item.creator_club} away={item.opponent_club} size={38} />\n                  </View>",
    'escudos matchup',
  );

  ui = replaceOnce(
    ui,
    "  clubStrip: { borderWidth: 1, borderColor: '#25445c', backgroundColor: C.panel2, borderRadius: 15, padding: 13 },",
    "  clubStrip: { borderWidth: 1, borderColor: '#25445c', backgroundColor: C.panel2, borderRadius: 15, padding: 13, flexDirection: 'row', alignItems: 'center', gap: 12 },",
    'style clubStrip',
  );

  fs.writeFileSync(path, ui);
}

patchBotParity();
patchMatchSearch();
console.log('Team badges HQ patch applied.');
