import React from 'react';
import { Image, Text, View } from 'react-native';
import type { ImageSourcePropType, ImageStyle, StyleProp } from 'react-native';
import { ATLETICO_BADGE_DATA_URI } from './atleticoBadge';

// Snapshot exacto anterior a la regresión de escudos. IMPORTANTE: nunca apuntar
// estos archivos a /main porque los saneados posteriores reemplazaron algunos
// PNG por miniaturas degradadas/con fondo. Al fijar el commit, recuperamos los
// mismos assets que mostraba el APK bueno y quedan inmunes a cambios futuros.
const GOOD_BADGE_COMMIT = '23835b53e061c77fe6af1fdaeec0ebd564bcb1b6';
const RAW = `https://raw.githubusercontent.com/agustinperalta745-ai/AJAP-TRANSFER-MARKET-V-0.1/${GOOD_BADGE_COMMIT}/mobile/assets/teams`;
const remote = (file: string): ImageSourcePropType => ({ uri: `${RAW}/${file}` });

// Excepciones realmente HQ:
// - Ajax: PNG >=512px con transparencia y blanco interior, preparado en CI.
// - Monaco: export vectorial validado que ya estaba aprobado.
// - Atletico: render 512px transparente del EPS original enviado para AJPA.
const ASSETS = {
  ajax: require('../assets/team_badge_ajax_hq/ajax.png'),
  as_monaco: require('../assets/team_badge_test/as_monaco_hd.png'),
  aston_villa: remote('aston_villa.png'),
  atletico_madrid: { uri: ATLETICO_BADGE_DATA_URI } as ImageSourcePropType,
  benfica: remote('benfica.png'),
  bolton_wanderers: remote('bolton_wanderers.png'),
  everton: remote('everton.png'),
  feyenoord: remote('feyenoord.png'),
  fiorentina: remote('fiorentina.png'),
  fulham: remote('fulham.png'),
  galatasaray: remote('galatasaray.png'),
  lazio: remote('lazio.png'),
  manchester_city: remote('manchester_city.png'),
  middlesbrough: remote('middlesbrough.png'),
  olympique_lyon: remote('olympique_lyon.png'),
  olympique_marseille: remote('olympique_marseille.png'),
  porto: remote('porto.png'),
  psg: remote('psg.png'),
  real_betis: remote('real_betis.png'),
  sevilla: remote('sevilla.png'),
  torino: remote('torino.png'),
  tottenham_hotspur: remote('tottenham_hotspur.png'),
  villarreal: remote('villarreal.png'),
  west_ham_united: remote('west_ham_united.png'),
  zaragoza: remote('zaragoza.png'),
} satisfies Record<string, ImageSourcePropType>;

const normalizeClub = (club: string | null | undefined) =>
  String(club || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[._-]+/g, ' ')
    .replace(/[^a-z0-9 ]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

const BADGES: Record<string, ImageSourcePropType> = {
  ajax: ASSETS.ajax,
  monaco: ASSETS.as_monaco,
  'as monaco': ASSETS.as_monaco,
  'as monaco fc': ASSETS.as_monaco,
  'aston villa': ASSETS.aston_villa,
  'atletico madrid': ASSETS.atletico_madrid,
  'atletico de madrid': ASSETS.atletico_madrid,
  'club atletico de madrid': ASSETS.atletico_madrid,
  'atletico de madrid fc': ASSETS.atletico_madrid,
  'at madrid': ASSETS.atletico_madrid,
  benfica: ASSETS.benfica,
  'sl benfica': ASSETS.benfica,
  'real betis': ASSETS.real_betis,
  betis: ASSETS.real_betis,
  'bolton wanderers': ASSETS.bolton_wanderers,
  bolton: ASSETS.bolton_wanderers,
  everton: ASSETS.everton,
  feyenoord: ASSETS.feyenoord,
  fiorentina: ASSETS.fiorentina,
  fulham: ASSETS.fulham,
  galatasaray: ASSETS.galatasaray,
  lazio: ASSETS.lazio,
  'ss lazio': ASSETS.lazio,
  lyon: ASSETS.olympique_lyon,
  'olympique lyonnais': ASSETS.olympique_lyon,
  'olympique de lyon': ASSETS.olympique_lyon,
  'manchester city': ASSETS.manchester_city,
  'man city': ASSETS.manchester_city,
  marsella: ASSETS.olympique_marseille,
  marseille: ASSETS.olympique_marseille,
  'olympique de marsella': ASSETS.olympique_marseille,
  'olympique de marseille': ASSETS.olympique_marseille,
  middlesbrough: ASSETS.middlesbrough,
  middle: ASSETS.middlesbrough,
  psg: ASSETS.psg,
  'paris saint germain': ASSETS.psg,
  porto: ASSETS.porto,
  'fc porto': ASSETS.porto,
  sevilla: ASSETS.sevilla,
  'sevilla fc': ASSETS.sevilla,
  torino: ASSETS.torino,
  'torino fc': ASSETS.torino,
  tottenham: ASSETS.tottenham_hotspur,
  'tottenham hotspur': ASSETS.tottenham_hotspur,
  villareal: ASSETS.villarreal,
  villarreal: ASSETS.villarreal,
  'villarreal cf': ASSETS.villarreal,
  'west ham': ASSETS.west_ham_united,
  'west ham united': ASSETS.west_ham_united,
  zaragoza: ASSETS.zaragoza,
  'real zaragoza': ASSETS.zaragoza,
};

export function getTeamBadge(club: string | null | undefined): ImageSourcePropType | null {
  const key = normalizeClub(club);
  if (!key || key === 'jugador libre') return null;
  return BADGES[key] ?? null;
}

export function ClubBadge({
  club,
  size = 72,
  style,
}: {
  club: string | null | undefined;
  size?: number;
  style?: StyleProp<ImageStyle>;
}) {
  const source = getTeamBadge(club);
  if (!source) return null;
  return (
    <Image
      source={source}
      resizeMode="contain"
      fadeDuration={0}
      accessibilityLabel={`Escudo de ${String(club || 'club')}`}
      style={[{ width: size, height: size, backgroundColor: 'transparent' }, style]}
    />
  );
}

export function ClubMatchup({
  home,
  away,
  size = 58,
}: {
  home: string | null | undefined;
  away: string | null | undefined;
  size?: number;
}) {
  const homeBadge = getTeamBadge(home);
  const awayBadge = getTeamBadge(away);
  if (!homeBadge && !awayBadge) return null;
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 8 }}>
      {homeBadge ? <ClubBadge club={home} size={size} /> : null}
      <Text style={{ color: '#92a0ad', fontWeight: '800' }}>VS</Text>
      {awayBadge ? <ClubBadge club={away} size={size} /> : null}
    </View>
  );
}
