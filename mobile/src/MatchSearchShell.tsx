import React, { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import BotParityAppV2 from './BotParityAppV2';
import { apiRequest } from './api';

type RoomAccess = {
  pes_lobby: string;
  room_name: string;
  password: string | null;
};

type MatchSearchItem = {
  id: number;
  creator_club: string;
  status: 'OPEN' | 'MATCHED' | string;
  opponent_club: string | null;
  created_at: string;
  matched_at: string | null;
  is_owner: boolean;
  is_opponent: boolean;
  can_join: boolean;
  blocked_reason: string | null;
  room_access?: RoomAccess;
};

type MatchSearchPayload = {
  items: MatchSearchItem[];
  viewer_club: string | null;
};

const C = {
  bg: '#02060a',
  panel: 'rgba(8,18,28,0.96)',
  panel2: 'rgba(11,24,36,0.96)',
  border: '#1f3447',
  blue: '#2d92ff',
  blueSoft: '#8ac5ff',
  white: '#f7fbff',
  muted: '#92a0ad',
  green: '#45d47b',
  red: '#ff7880',
  orange: '#ffc36f',
};

const errorText = (error: unknown) =>
  typeof error === 'object' && error && 'message' in error
    ? String((error as { message?: string }).message)
    : 'No se pudo completar la operación.';

export default function MatchSearchShell() {
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [items, setItems] = useState<MatchSearchItem[]>([]);
  const [viewerClub, setViewerClub] = useState<string | null>(null);
  const [lobby, setLobby] = useState('');
  const [room, setRoom] = useState('');
  const [password, setPassword] = useState('');

  const load = async (quiet = false) => {
    if (!quiet) setLoading(true);
    try {
      const result = await apiRequest<MatchSearchPayload>('/api/v1/match-searches');
      setItems(result.items ?? []);
      setViewerClub(result.viewer_club ?? null);
    } catch (error) {
      if (!quiet) Alert.alert('Buscar Partido', errorText(error));
    } finally {
      if (!quiet) setLoading(false);
    }
  };

  useEffect(() => {
    if (!open) return;
    void load();
    const timer = setInterval(() => void load(true), 8000);
    return () => clearInterval(timer);
  }, [open]);

  const submit = async () => {
    if (!lobby.trim() || !room.trim()) {
      Alert.alert('Faltan datos', 'Completá el vestíbulo de PES y el nombre de la sala.');
      return;
    }
    setBusyId(-1);
    try {
      await apiRequest('/api/v1/match-searches', {
        method: 'POST',
        body: JSON.stringify({
          pes_lobby: lobby.trim(),
          room_name: room.trim(),
          password: password.trim(),
        }),
      });
      setLobby('');
      setRoom('');
      setPassword('');
      setCreating(false);
      await load(true);
    } catch (error) {
      Alert.alert('No se pudo publicar', errorText(error));
    } finally {
      setBusyId(null);
    }
  };

  const join = async (item: MatchSearchItem) => {
    setBusyId(item.id);
    try {
      const result = await apiRequest<{
        creator_club: string;
        opponent_club: string;
        room_access: RoomAccess;
      }>(`/api/v1/match-searches/${item.id}/join`, {
        method: 'POST',
        body: '{}',
      });
      const access = result.room_access;
      Alert.alert(
        '⚽ Rival encontrado',
        `${result.opponent_club} vs ${result.creator_club}\n\nVestíbulo: ${access.pes_lobby}\nSala: ${access.room_name}\nContraseña: ${access.password || 'Sin contraseña'}`,
      );
      await load(true);
    } catch (error) {
      Alert.alert('No podés entrar', errorText(error));
      await load(true);
    } finally {
      setBusyId(null);
    }
  };

  const cancel = (item: MatchSearchItem) => {
    Alert.alert('Cancelar búsqueda', `¿Cancelar la búsqueda de ${item.creator_club}?`, [
      { text: 'Volver', style: 'cancel' },
      {
        text: 'CANCELAR BÚSQUEDA',
        style: 'destructive',
        onPress: async () => {
          setBusyId(item.id);
          try {
            await apiRequest(`/api/v1/match-searches/${item.id}/cancel`, {
              method: 'POST',
              body: '{}',
            });
            await load(true);
          } catch (error) {
            Alert.alert('Buscar Partido', errorText(error));
          } finally {
            setBusyId(null);
          }
        },
      },
    ]);
  };

  const openRoomText = (access: RoomAccess) =>
    `Vestíbulo: ${access.pes_lobby}\nSala: ${access.room_name}\nContraseña: ${access.password || 'Sin contraseña'}`;

  return (
    <View style={s.root}>
      <BotParityAppV2 />

      {!open ? (
        <Pressable style={({ pressed }) => [s.entry, pressed && { opacity: 0.76 }]} onPress={() => setOpen(true)}>
          <Text style={s.entryEmoji}>⚽</Text>
          <View style={{ flex: 1 }}>
            <Text style={s.entryTitle}>BUSCAR PARTIDO</Text>
            <Text style={s.entrySub}>Encontrá un rival disponible</Text>
          </View>
          <Text style={s.chevron}>›</Text>
        </Pressable>
      ) : null}

      {open ? (
        <View style={s.overlay}>
          <View style={s.header}>
            <Pressable onPress={() => setOpen(false)} style={s.headerButton}>
              <Text style={s.headerButtonText}>‹ VOLVER</Text>
            </Pressable>
            <View style={{ flex: 1 }}>
              <Text style={s.eyebrow}>AJPA · PARTIDOS</Text>
              <Text style={s.title}>Buscar Partido</Text>
            </View>
            <Pressable onPress={() => void load()} style={s.refreshButton}>
              <Text style={s.refreshText}>↻</Text>
            </Pressable>
          </View>

          <ScrollView contentContainerStyle={s.content} keyboardShouldPersistTaps="handled">
            <Text style={s.subtitle}>
              Las búsquedas son públicas. Los datos de la sala solo se revelan al rival que acepta.
            </Text>

            {viewerClub ? (
              <View style={s.clubStrip}>
                <Text style={s.clubStripLabel}>TU CLUB</Text>
                <Text style={s.clubStripValue}>{viewerClub}</Text>
              </View>
            ) : (
              <View style={s.notice}>
                <Text style={s.noticeTitle}>Podés ver las búsquedas</Text>
                <Text style={s.noticeText}>Para crear o aceptar un partido, vinculá Discord y tené un club asignado.</Text>
              </View>
            )}

            {viewerClub && !creating ? (
              <Pressable style={({ pressed }) => [s.primary, pressed && { opacity: 0.75 }]} onPress={() => setCreating(true)}>
                <Text style={s.primaryText}>＋ BUSCAR RIVAL</Text>
              </Pressable>
            ) : null}

            {creating ? (
              <View style={s.formCard}>
                <Text style={s.formTitle}>{viewerClub} está buscando rival</Text>

                <Text style={s.label}>VESTÍBULO DE PES</Text>
                <TextInput
                  style={s.input}
                  value={lobby}
                  onChangeText={setLobby}
                  placeholder="Ej: Vestíbulo 1"
                  placeholderTextColor="#657382"
                  maxLength={80}
                />

                <Text style={s.label}>NOMBRE DE LA SALA</Text>
                <TextInput
                  style={s.input}
                  value={room}
                  onChangeText={setRoom}
                  placeholder="Ej: AJPA Sevilla"
                  placeholderTextColor="#657382"
                  maxLength={80}
                />

                <Text style={s.label}>CONTRASEÑA · OPCIONAL</Text>
                <TextInput
                  style={s.input}
                  value={password}
                  onChangeText={setPassword}
                  placeholder="Sin contraseña"
                  placeholderTextColor="#657382"
                  maxLength={80}
                />

                <View style={s.actionRow}>
                  <Pressable disabled={busyId === -1} style={[s.primarySmall, busyId === -1 && s.disabled]} onPress={submit}>
                    <Text style={s.primaryText}>{busyId === -1 ? 'PUBLICANDO…' : 'PUBLICAR BÚSQUEDA'}</Text>
                  </Pressable>
                  <Pressable disabled={busyId === -1} style={s.ghost} onPress={() => setCreating(false)}>
                    <Text style={s.ghostText}>CANCELAR</Text>
                  </Pressable>
                </View>
              </View>
            ) : null}

            <Text style={s.section}>🔎 EQUIPOS BUSCANDO RIVAL</Text>
            {loading ? <ActivityIndicator color={C.blue} size="large" /> : null}

            {!loading && items.length === 0 ? (
              <View style={s.emptyCard}>
                <Text style={s.emptyTitle}>No hay búsquedas activas</Text>
                <Text style={s.noticeText}>Cuando un equipo publique una sala, aparecerá acá.</Text>
              </View>
            ) : null}

            {items.map((item) => (
              <View key={item.id} style={[s.searchCard, item.status === 'MATCHED' && s.matchedCard]}>
                <View style={s.cardHeader}>
                  <View style={{ flex: 1 }}>
                    <Text style={s.cardEyebrow}>{item.status === 'MATCHED' ? '✅ RIVAL ENCONTRADO' : '🟢 DISPONIBLE AHORA'}</Text>
                    <Text style={s.cardTitle}>{item.creator_club.toUpperCase()} BUSCA RIVAL</Text>
                  </View>
                  <Text style={s.ball}>⚽</Text>
                </View>

                {item.status === 'MATCHED' && item.opponent_club ? (
                  <Text style={s.matchup}>{item.creator_club} vs {item.opponent_club}</Text>
                ) : null}

                {item.room_access && item.status === 'MATCHED' ? (
                  <View style={s.accessBox}>
                    <Text style={s.accessTitle}>DATOS PARA ENTRAR A LA CANCHA</Text>
                    <Text style={s.accessText}>{openRoomText(item.room_access)}</Text>
                  </View>
                ) : null}

                {item.status === 'OPEN' && item.is_owner ? (
                  <Pressable disabled={busyId === item.id} style={[s.danger, busyId === item.id && s.disabled]} onPress={() => cancel(item)}>
                    <Text style={s.dangerText}>CANCELAR BÚSQUEDA</Text>
                  </Pressable>
                ) : null}

                {item.status === 'OPEN' && !item.is_owner ? (
                  <>
                    <Pressable
                      disabled={!item.can_join || busyId === item.id}
                      style={[s.join, (!item.can_join || busyId === item.id) && s.disabled]}
                      onPress={() => join(item)}
                    >
                      <Text style={s.joinText}>{busyId === item.id ? 'ENTRANDO…' : '⚽ IR A LA CANCHA'}</Text>
                    </Pressable>
                    {!item.can_join && item.blocked_reason ? (
                      <Text style={s.blocked}>🔒 {item.blocked_reason}</Text>
                    ) : null}
                  </>
                ) : null}

                {item.status === 'MATCHED' && item.is_owner ? (
                  <Pressable disabled={busyId === item.id} style={[s.danger, busyId === item.id && s.disabled]} onPress={() => cancel(item)}>
                    <Text style={s.dangerText}>CERRAR / CANCELAR PARTIDO</Text>
                  </Pressable>
                ) : null}
              </View>
            ))}
          </ScrollView>
        </View>
      ) : null}
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.bg },
  entry: {
    position: 'absolute',
    right: 14,
    bottom: 18,
    left: 14,
    minHeight: 62,
    borderRadius: 18,
    borderWidth: 1,
    borderColor: '#2d5d82',
    backgroundColor: 'rgba(5,18,29,0.97)',
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    zIndex: 20,
  },
  entryEmoji: { fontSize: 25, marginRight: 12 },
  entryTitle: { color: C.white, fontSize: 14, fontWeight: '900', letterSpacing: 0.8 },
  entrySub: { color: C.muted, fontSize: 10, marginTop: 3 },
  chevron: { color: C.blueSoft, fontSize: 28 },
  overlay: { ...StyleSheet.absoluteFillObject, backgroundColor: C.bg, zIndex: 50 },
  header: {
    minHeight: 70,
    paddingHorizontal: 14,
    borderBottomWidth: 1,
    borderBottomColor: '#152838',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  headerButton: { paddingVertical: 12, paddingRight: 8 },
  headerButtonText: { color: C.blueSoft, fontSize: 10, fontWeight: '900', letterSpacing: 0.8 },
  refreshButton: { width: 42, height: 42, borderRadius: 14, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: C.border },
  refreshText: { color: C.blueSoft, fontSize: 22, fontWeight: '900' },
  eyebrow: { color: C.blue, fontSize: 9, fontWeight: '900', letterSpacing: 1.5 },
  title: { color: C.white, fontSize: 23, fontWeight: '900' },
  content: { padding: 16, paddingBottom: 44, gap: 12 },
  subtitle: { color: C.muted, fontSize: 12, lineHeight: 18 },
  clubStrip: { borderWidth: 1, borderColor: '#25445c', backgroundColor: C.panel2, borderRadius: 15, padding: 13 },
  clubStripLabel: { color: C.blueSoft, fontSize: 8, fontWeight: '900', letterSpacing: 1.2 },
  clubStripValue: { color: C.white, fontSize: 17, fontWeight: '900', marginTop: 4 },
  notice: { backgroundColor: C.panel, borderWidth: 1, borderColor: C.border, borderRadius: 16, padding: 14 },
  noticeTitle: { color: C.white, fontSize: 14, fontWeight: '900' },
  noticeText: { color: C.muted, fontSize: 11, lineHeight: 16, marginTop: 5 },
  primary: { minHeight: 50, borderRadius: 14, alignItems: 'center', justifyContent: 'center', backgroundColor: C.blue },
  primarySmall: { minHeight: 44, borderRadius: 12, alignItems: 'center', justifyContent: 'center', backgroundColor: C.blue, paddingHorizontal: 14 },
  primaryText: { color: C.white, fontSize: 10, fontWeight: '900', letterSpacing: 0.7 },
  formCard: { backgroundColor: C.panel2, borderWidth: 1, borderColor: C.blue, borderRadius: 18, padding: 15 },
  formTitle: { color: C.white, fontSize: 17, fontWeight: '900' },
  label: { color: C.blueSoft, fontSize: 9, fontWeight: '900', letterSpacing: 1.1, marginTop: 13, marginBottom: 6 },
  input: { minHeight: 48, borderRadius: 12, borderWidth: 1, borderColor: '#29435a', backgroundColor: '#07131d', color: C.white, paddingHorizontal: 13, fontSize: 16 },
  actionRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 14 },
  ghost: { minHeight: 44, borderRadius: 12, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: '#30475b', paddingHorizontal: 14 },
  ghostText: { color: C.white, fontSize: 10, fontWeight: '900' },
  section: { color: C.blueSoft, fontSize: 10, fontWeight: '900', letterSpacing: 1.3, marginTop: 5 },
  emptyCard: { backgroundColor: C.panel, borderWidth: 1, borderColor: C.border, borderRadius: 18, padding: 18, alignItems: 'center' },
  emptyTitle: { color: C.white, fontSize: 15, fontWeight: '900' },
  searchCard: { backgroundColor: C.panel, borderWidth: 1, borderColor: '#29435a', borderRadius: 20, padding: 15 },
  matchedCard: { borderColor: '#285d40', backgroundColor: 'rgba(7,27,18,0.96)' },
  cardHeader: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  cardEyebrow: { color: C.green, fontSize: 9, fontWeight: '900', letterSpacing: 1.2 },
  cardTitle: { color: C.white, fontSize: 18, lineHeight: 23, fontWeight: '900', marginTop: 5 },
  ball: { fontSize: 28 },
  matchup: { color: C.blueSoft, fontSize: 13, fontWeight: '800', marginTop: 10 },
  join: { minHeight: 48, borderRadius: 13, backgroundColor: '#176a3a', alignItems: 'center', justifyContent: 'center', marginTop: 14 },
  joinText: { color: C.white, fontSize: 11, fontWeight: '900', letterSpacing: 0.7 },
  danger: { minHeight: 45, borderRadius: 13, backgroundColor: '#7e2c35', alignItems: 'center', justifyContent: 'center', marginTop: 14 },
  dangerText: { color: C.white, fontSize: 10, fontWeight: '900' },
  disabled: { opacity: 0.38 },
  blocked: { color: C.orange, fontSize: 10.5, lineHeight: 15, marginTop: 8 },
  accessBox: { borderWidth: 1, borderColor: '#2a6644', backgroundColor: 'rgba(5,20,13,0.92)', borderRadius: 14, padding: 12, marginTop: 12 },
  accessTitle: { color: C.green, fontSize: 9, fontWeight: '900', letterSpacing: 1 },
  accessText: { color: C.white, fontSize: 13, lineHeight: 20, marginTop: 6, fontWeight: '700' },
});
