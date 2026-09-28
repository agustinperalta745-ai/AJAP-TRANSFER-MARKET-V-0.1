import React, { useMemo } from 'react';
import {
  Image,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import MaterialCommunityIcons from '@expo/vector-icons/MaterialCommunityIcons';

import { AJPA_LOGO_DATA_URI } from './branding';
import { ClubBadge, getClubTheme } from './teamBadges';

type Player = {
  name: string;
  ovr: number;
  positions: string;
  club: string;
  operation: 'INTERCAMBIO' | 'TRANSFERENCIA';
  price: string;
  note: string;
};

const PLAYERS: Player[] = [
  {
    name: 'Ribery',
    ovr: 85,
    positions: 'AMF / WF',
    club: 'Olympique de Marsella',
    operation: 'INTERCAMBIO',
    price: '$ 0',
    note: 'Busca: Carew',
  },
  {
    name: 'Juan Carlos',
    ovr: 81,
    positions: 'GK',
    club: 'Villarreal CF',
    operation: 'TRANSFERENCIA',
    price: '$ 3.500.000',
    note: 'Sin observaciones',
  },
  {
    name: 'Gerard',
    ovr: 88,
    positions: 'CMF / DMF',
    club: 'AS Monaco',
    operation: 'TRANSFERENCIA',
    price: '$ 8.000.000',
    note: 'Sin observaciones',
  },
  {
    name: 'Huntelaar',
    ovr: 82,
    positions: 'CF',
    club: 'Ajax',
    operation: 'TRANSFERENCIA',
    price: '$ 6.000.000',
    note: 'Sin observaciones',
  },
];

function MarketCard({ player }: { player: Player }) {
  const theme = useMemo(() => getClubTheme(player.club), [player.club]);
  const isSwap = player.operation === 'INTERCAMBIO';
  const operationColor = isSwap ? '#38aef8' : '#42d58a';

  return (
    <View
      style={[
        s.card,
        {
          borderColor: theme.primary + '8f',
          shadowColor: theme.primary,
        },
      ]}
    >
      <View
        pointerEvents="none"
        style={[
          s.clubGlow,
          {
            backgroundColor: theme.primary,
          },
        ]}
      />
      <View pointerEvents="none" style={s.badgeWatermark}>
        <ClubBadge club={player.club} size={92} style={{ opacity: 0.2 }} />
      </View>

      <View style={s.cardTop}>
        <View
          style={[
            s.ovrBox,
            {
              backgroundColor: theme.secondary,
              borderColor: theme.accent + 'c7',
            },
          ]}
        >
          <Text style={s.ovrNumber}>{player.ovr}</Text>
          <Text style={s.ovrLabel}>OVR</Text>
        </View>

        <View style={s.identity}>
          <Text numberOfLines={1} style={s.playerName}>{player.name}</Text>
          <View style={s.positionPill}>
            <Text style={s.positionText}>{player.positions}</Text>
          </View>
          <View style={s.clubLine}>
            <ClubBadge club={player.club} size={28} />
            <Text numberOfLines={1} style={s.clubName}>{player.club}</Text>
          </View>
        </View>

        <View style={s.operationCol}>
          <Text style={s.operationEyebrow}>TIPO DE OPERACIÓN</Text>
          <View style={s.operationLine}>
            <MaterialCommunityIcons
              name={isSwap ? 'swap-horizontal-bold' : 'cash-sync'}
              size={20}
              color={operationColor}
            />
            <Text style={[s.operationText, { color: operationColor }]}>
              {player.operation}
            </Text>
          </View>
          <View style={s.priceLine}>
            <MaterialCommunityIcons name="tag-outline" size={17} color="#ecf5fb" />
            <Text style={s.priceText}>{player.price}</Text>
          </View>
        </View>
      </View>

      <View style={s.divider} />

      <View style={s.cardBottom}>
        <View style={s.noteLine}>
          <MaterialCommunityIcons
            name="text-box-outline"
            size={20}
            color="#86a2b6"
          />
          <Text numberOfLines={1} style={s.noteText}>{player.note}</Text>
        </View>

        <View style={s.actions}>
          <Pressable style={({ pressed }) => [s.statsButton, pressed && s.pressed]}>
            <MaterialCommunityIcons name="chart-bar" size={20} color="#4dbbff" />
            <Text style={s.statsButtonText}>VER ESTADÍSTICAS</Text>
          </Pressable>
          <Pressable style={({ pressed }) => [s.offerButton, pressed && s.pressed]}>
            <MaterialCommunityIcons name="handshake-outline" size={21} color="#fff" />
            <Text style={s.offerButtonText}>HACER OFERTA</Text>
          </Pressable>
        </View>
      </View>
    </View>
  );
}

export default function MarketPreview({ onHome }: { onHome: () => void }) {
  return (
    <View style={s.root}>
      <ScrollView contentContainerStyle={s.content} showsVerticalScrollIndicator={false}>
        <View style={s.brandHeader}>
          <View style={s.brandLeft}>
            <Image source={{ uri: AJPA_LOGO_DATA_URI }} style={s.logo} resizeMode="contain" />
            <View>
              <Text style={s.brand}>AJPA</Text>
              <Text style={s.brandSub}>ASOCIACIÓN DE JUGADORES DE PES ARGENTINA</Text>
            </View>
          </View>
          <View style={s.onlineDot} />
        </View>

        <View style={s.userRow}>
          <Pressable onPress={onHome} style={({ pressed }) => [s.backButton, pressed && s.pressed]}>
            <MaterialCommunityIcons name="chevron-left" size={22} color="#8fd2ff" />
            <Text style={s.backText}>VOLVER</Text>
          </Pressable>
          <View style={s.userCard}>
            <View>
              <Text style={s.userTitle}>Hola, DT</Text>
              <Text style={s.userSub}>Conectado a AJPA</Text>
            </View>
            <MaterialCommunityIcons name="chevron-right" size={23} color="#3bb9ff" />
          </View>
        </View>

        <View style={s.sectionHeader}>
          <View style={{ flex: 1 }}>
            <Text style={s.eyebrow}>MERCADO</Text>
            <Text style={s.title}>Transferibles</Text>
            <Text style={s.subtitle}>Jugadores disponibles de la comunidad AJPA.</Text>
          </View>

          <View style={s.headerActions}>
            <Pressable style={({ pressed }) => [s.squareButton, pressed && s.pressed]}>
              <MaterialCommunityIcons name="magnify" size={26} color="#ecf7ff" />
            </Pressable>
            <Pressable style={({ pressed }) => [s.filterButton, pressed && s.pressed]}>
              <MaterialCommunityIcons name="filter-variant" size={21} color="#ecf7ff" />
              <Text style={s.filterText}>Filtrar</Text>
              <MaterialCommunityIcons name="chevron-down" size={20} color="#3cbaff" />
            </Pressable>
          </View>
        </View>

        <View style={s.listLabel}>
          <MaterialCommunityIcons name="earth" size={19} color="#45bbff" />
          <Text style={s.listLabelText}>TRANSFERIBLES DE OTROS EQUIPOS · 8</Text>
        </View>

        <View style={s.cards}>
          {PLAYERS.map(player => (
            <MarketCard key={player.name} player={player} />
          ))}
        </View>
      </ScrollView>

      <View style={s.bottomNav}>
        <Pressable onPress={onHome} style={s.navItem}>
          <MaterialCommunityIcons name="home" size={25} color="#899cab" />
          <Text style={s.navLabel}>Inicio</Text>
        </Pressable>
        <View style={s.navItem}>
          <MaterialCommunityIcons name="handshake" size={25} color="#35b9ff" />
          <Text style={[s.navLabel, s.navActive]}>Mercado</Text>
        </View>
        <View style={s.navItem}>
          <MaterialCommunityIcons name="shield" size={25} color="#899cab" />
          <Text style={s.navLabel}>Mi Club</Text>
        </View>
        <View style={s.navItem}>
          <MaterialCommunityIcons name="chart-bar" size={25} color="#899cab" />
          <Text style={s.navLabel}>Liga</Text>
        </View>
        <View style={s.navItem}>
          <MaterialCommunityIcons name="trophy" size={25} color="#899cab" />
          <Text style={s.navLabel}>Copas</Text>
        </View>
        <View style={s.navItem}>
          <MaterialCommunityIcons name="dots-horizontal" size={25} color="#899cab" />
          <Text style={s.navLabel}>Más</Text>
        </View>
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: '#06111d',
  },
  content: {
    paddingHorizontal: 14,
    paddingTop: 14,
    paddingBottom: 104,
  },
  brandHeader: {
    minHeight: 78,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  brandLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
  },
  logo: {
    width: 58,
    height: 58,
    marginRight: 10,
  },
  brand: {
    color: '#f7fbff',
    fontSize: 32,
    lineHeight: 34,
    fontWeight: '900',
    letterSpacing: 1.2,
  },
  brandSub: {
    color: '#67bff4',
    fontSize: 8.5,
    lineHeight: 12,
    fontWeight: '900',
    letterSpacing: 1.8,
  },
  onlineDot: {
    width: 11,
    height: 11,
    borderRadius: 6,
    backgroundColor: '#35df72',
    marginRight: 3,
  },
  userRow: {
    marginTop: 8,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 10,
  },
  backButton: {
    height: 46,
    borderRadius: 15,
    borderWidth: 1,
    borderColor: '#245374',
    backgroundColor: '#0b2030',
    paddingHorizontal: 12,
    flexDirection: 'row',
    alignItems: 'center',
  },
  backText: {
    color: '#8fd2ff',
    fontSize: 11,
    fontWeight: '900',
    letterSpacing: 0.4,
    marginLeft: -2,
  },
  userCard: {
    width: 150,
    minHeight: 58,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: '#245374',
    backgroundColor: '#0b2030',
    paddingHorizontal: 12,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  userTitle: {
    color: '#f3f7fa',
    fontSize: 14,
    fontWeight: '900',
  },
  userSub: {
    color: '#8c9ba8',
    fontSize: 9.5,
    marginTop: 2,
  },
  sectionHeader: {
    marginTop: 20,
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: 12,
  },
  eyebrow: {
    color: '#48b9f8',
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 2.1,
  },
  title: {
    color: '#f6fbff',
    fontSize: 31,
    fontWeight: '900',
    letterSpacing: -0.5,
    marginTop: 2,
  },
  subtitle: {
    color: '#92a3af',
    fontSize: 11,
    marginTop: 4,
  },
  headerActions: {
    flexDirection: 'row',
    gap: 8,
  },
  squareButton: {
    width: 47,
    height: 47,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: '#245374',
    backgroundColor: '#0b2030',
    alignItems: 'center',
    justifyContent: 'center',
  },
  filterButton: {
    height: 47,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: '#245374',
    backgroundColor: '#0b2030',
    paddingHorizontal: 12,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 7,
  },
  filterText: {
    color: '#e9f4fb',
    fontSize: 12,
    fontWeight: '800',
  },
  listLabel: {
    marginTop: 18,
    marginBottom: 9,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 7,
  },
  listLabelText: {
    color: '#43baff',
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 1.5,
  },
  cards: {
    gap: 10,
  },
  card: {
    minHeight: 196,
    borderRadius: 20,
    borderWidth: 1,
    backgroundColor: '#0c2232',
    padding: 13,
    overflow: 'hidden',
    shadowOpacity: 0.2,
    shadowRadius: 14,
    shadowOffset: { width: 0, height: 7 },
    elevation: 4,
  },
  clubGlow: {
    position: 'absolute',
    width: 200,
    height: 170,
    right: -70,
    top: -65,
    borderRadius: 110,
    opacity: 0.11,
  },
  badgeWatermark: {
    position: 'absolute',
    right: 8,
    top: 18,
  },
  cardTop: {
    minHeight: 105,
    flexDirection: 'row',
    alignItems: 'flex-start',
  },
  ovrBox: {
    width: 62,
    height: 74,
    borderRadius: 15,
    borderWidth: 1.2,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 11,
  },
  ovrNumber: {
    color: '#fff',
    fontSize: 27,
    lineHeight: 29,
    fontWeight: '900',
  },
  ovrLabel: {
    color: '#dce8f0',
    fontSize: 9,
    fontWeight: '700',
    marginTop: 2,
  },
  identity: {
    flex: 1,
    minWidth: 0,
    paddingTop: 2,
    paddingRight: 6,
  },
  playerName: {
    color: '#f8fbfd',
    fontSize: 18,
    fontWeight: '900',
  },
  positionPill: {
    alignSelf: 'flex-start',
    minWidth: 48,
    marginTop: 6,
    paddingHorizontal: 9,
    paddingVertical: 4,
    borderRadius: 9,
    borderWidth: 1,
    borderColor: '#2b647f',
    backgroundColor: 'rgba(12,46,64,0.9)',
  },
  positionText: {
    color: '#bfd4e2',
    fontSize: 9.5,
    fontWeight: '800',
  },
  clubLine: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 7,
    gap: 6,
    maxWidth: 150,
  },
  clubName: {
    flex: 1,
    color: '#b2c4d0',
    fontSize: 10.5,
  },
  operationCol: {
    width: 120,
    paddingTop: 2,
    paddingLeft: 8,
    borderLeftWidth: 1,
    borderLeftColor: '#25516d',
  },
  operationEyebrow: {
    color: '#7f9db1',
    fontSize: 7.2,
    fontWeight: '900',
    letterSpacing: 1,
  },
  operationLine: {
    marginTop: 6,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
  },
  operationText: {
    flex: 1,
    fontSize: 10.5,
    fontWeight: '900',
  },
  priceLine: {
    marginTop: 7,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
  },
  priceText: {
    color: '#f2f7fa',
    fontSize: 11.5,
    fontWeight: '900',
  },
  divider: {
    height: 1,
    backgroundColor: '#27546e',
    opacity: 0.8,
    marginVertical: 10,
  },
  cardBottom: {
    gap: 9,
  },
  noteLine: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 7,
    minHeight: 25,
  },
  noteText: {
    flex: 1,
    color: '#9eafba',
    fontSize: 10.5,
  },
  actions: {
    flexDirection: 'row',
    gap: 8,
  },
  statsButton: {
    flex: 1,
    minHeight: 46,
    borderRadius: 13,
    borderWidth: 1,
    borderColor: '#2aaeff',
    backgroundColor: 'rgba(6,21,33,0.86)',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 7,
    paddingHorizontal: 8,
  },
  statsButtonText: {
    color: '#dfeff8',
    fontSize: 9.8,
    fontWeight: '900',
  },
  offerButton: {
    flex: 1,
    minHeight: 46,
    borderRadius: 13,
    backgroundColor: '#239cf2',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 7,
    paddingHorizontal: 8,
  },
  offerButtonText: {
    color: '#fff',
    fontSize: 9.8,
    fontWeight: '900',
  },
  pressed: {
    opacity: 0.72,
    transform: [{ scale: 0.985 }],
  },
  bottomNav: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    height: 74,
    paddingHorizontal: 6,
    borderTopWidth: 1,
    borderTopColor: '#17364a',
    backgroundColor: 'rgba(5,16,26,0.98)',
    flexDirection: 'row',
    alignItems: 'center',
  },
  navItem: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    height: 64,
  },
  navLabel: {
    color: '#899cab',
    fontSize: 8.5,
    fontWeight: '700',
    marginTop: 2,
  },
  navActive: {
    color: '#35b9ff',
  },
});
