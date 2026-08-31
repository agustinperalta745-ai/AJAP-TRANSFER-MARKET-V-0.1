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

type MatchResult = {
  home_team: string;
  away_team: string;
  home_goals: number;
  away_goals: number;
};

type MatchSearchItem = {
  id: number;
  creator_club: string;
  status: 'OPEN' | 'MATCHED' | 'COMPLETED' | string;
  opponent_club: string | null;
  created_at: string;
  expires_at: string | null;
  matched_at: string | null;
  completed_at: string | null;
  is_owner: boolean;
  is_opponent: boolean;
  can_join: boolean;
  blocked_reason: string | null;
  result: MatchResult | null;
  room_access?: RoomAccess;
};

type MatchSearchPayload = {
  items: MatchSearchItem[];
  viewer_club: string | null;
};

type CreateSearchResult = {
  id: number;
  status: 'OPEN' | 'MATCHED' | string;
  creator_club: string;
  opponent_club?: string | null;
  auto_matched?: boolean;
  room_access?: RoomAccess;
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

const parseServerTime = (value: string | null | undefined) => {
  const raw = String(value || '').trim();
  if (!raw) return Number.NaN;
  if (raw.endsWith('Z') || /[+-]\d\d:\d\d$/.test(raw)) return Date.parse(raw);
  if (raw.includes('T')) return Date.parse(`${raw}Z`);
  return Date.parse(`${raw.replace(' ', 'T')}Z`);
};

const secondsUntilExpiry = (item: MatchSearchItem, nowMs: number) => {
  if (item.status !== 'OPEN') return 0;
  const expiry = parseServerTime(item.expires_at);
  if (!Number.isFinite(expiry)) return 0;
  return Math.max(0, Math.ceil((expiry - nowMs) / 1000));
};

const countdownText = (seconds: number) => {
  const safe = Math.max(0, seconds);
  const minutes = Math.floor(safe / 60);
  const rest = safe % 60;
  return `${String(minutes).padStart(2, '0')}:${String(rest).padStart(2, '0')}`;
};

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
  const [nowMs, setNowMs] = useState(Date.now());

  const load = async (quiet = false) => {
    if (!quiet) setLoading(true);
    try {
      const result = await apiRequest<MatchSearchPayload>('/api/v1/match-searches');
      setItems(result.items ?? []);
      setViewerClub(result.viewer_club ?? null);
      setNowMs(Date.now());
    } catch (error) {
      if (!quiet) Alert.alert('Buscar Partido', errorText(error));
    } finally {
      if (!quiet) setLoading(false);
    }
  };

  useEffect(() => {
    if (!open) return;
    void load();
    const refreshTimer = setInterval(() => void load(true), 8000);
    const countdownTimer = setInterval(() => setNowMs(Date.now()), 1000);
    return () => {
      clearInterval(refreshTimer);
      clearInterval(countdownTimer);
    };
  }, [open]);

  const submit = async () => {
    if (!lobby.trim() || !room.trim()) {
      Alert.alert('Faltan datos', 'Completá el vestíbulo de PES y el nombre de la sala.');
      return;
    }
    setBusyId(-1);
    try {
      const result = await apiRequest<CreateSearchResult>('/api/v1/match-searches', {
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

      if (result.status === 'MATCHED' && result.room_access && result.opponent_club) {
        const access = result.room_access;
        Alert.alert(
          result.auto_matched ? '⚡ Rival encontrado automáticamente' : '⚽ Rival encontrado',
          `${result.creator_club} vs ${result.opponent_club}\n\nVestíbulo: ${access.pes_lobby}\nSala: ${access.room_name}\nContraseña: ${access.password || 'Sin contraseña'}`,
        );
      }
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
        `${result.creator_club} vs ${result.opponent_club}\n\nVestíbulo: ${access.pes_lobby}\nSala: ${access.room_name}\nContraseña: ${access.password || 'Sin contraseña'}`,
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

  const visibleItems = items.filter(
    (item) => item.status !== 'OPEN' || secondsUntilExpiry(item, nowMs) > 0,
  );
  const hasActiveSearch = items.some(
    (item) =>
      (item.status === 'OPEN' || item.status === 'MATCHED') &&
      (item.is_owner || item.is_opponent),
  );

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
              Las búsquedas son públicas y duran como máximo 30 minutos. Si aparece otro club elegible buscando rival, el sistema los une automáticamente.
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

            {viewerClub && !creating && !hasActiveSearch ? (
              <Pressable style={({ pressed }) => [s.primary, pressed && { opacity: 0.75 }]} onPress={() => setCreating(true)}>
                <Text style={s.primaryText}>＋ BUSCAR RIVAL</Text>
              </Pressable>
            ) : null}

            {viewerClub && hasActiveSearch && !creating ? (
              <View style={s.activeNotice}>
                <Text style={s.activeNoticeTitle}>⚽ YA TENÉS UN PARTIDO ACTIVO</Text>
                <Text style={s.activeNoticeText}>Terminá o cancelá el actual antes de iniciar otra búsqueda.</Text>
              </View>
            ) : null}

            {creating ? (
              <View style={s.formCard}>
                <Text style={s.formTitle}>{viewerClub} está buscando rival</Text>
                <Text style={s.formHint}>La publicación vence automáticamente a los 30 minutos si nadie la toma.</Text>

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
                    <Text style={s.primaryText}>{busyId === -1 ? 'BUSCANDO…' : 'PUBLICAR BÚSQUEDA'}</Text>
                  </Pressable>
                  <Pressable disabled={busyId === -1} style={s.ghost} onPress={() => setCreating(false)}>
                    <Text style={s.ghostText}>CANCELAR</Text>
                  </Pressable>
                </View>
              </View>
            ) : null}

            <Text style={s.section}>🔎 EQUIPOS BUSCANDO RIVAL</Text>
            {loading ? <ActivityIndicator color={C.blue} size="large" /> : null}

            {!loading && visibleItems.length === 0 ? (
              <View style={s.emptyCard}>
                <Text style={s.emptyTitle}>No hay búsquedas activas</Text>
                <Text style={s.noticeText}>Cuando un equipo publique una sala, aparecerá acá.</Text>
              </View>
            ) : null}

            {visibleItems.map((item) => {
              const secondsLeft = secondsUntilExpiry(item, nowMs);
              const isMatched = item.status === 'MATCHED';
              const isCompleted = item.status === 'COMPLETED';
              const cardTitle = isCompleted && item.opponent_club
                ? `${item.creator_club.toUpperCase()} VS ${item.opponent_club.toUpperCase()}`
                : `${item.creator_club.toUpperCase()} BUSCA RIVAL`;

              return (
                <View
                  key={item.id}
                  style={[
                    s.searchCard,
                    isMatched && s.matchedCard,
                    isCompleted && s.completedCard,
                  ]}
                >
                  <View style={s.cardHeader}>
                    <View style={{ flex: 1 }}>
                      <Text style={[s.cardEyebrow, isCompleted && s.completedEyebrow]}>
                        {isCompleted
                          ? '🏁 RESULTADO FINAL'
                          : isMatched
                            ? '✅ RIVAL ENCONTRADO'
                            : '🟢 DISPONIBLE AHORA'}
                      </Text>
                      <Text style={s.cardTitle}>{cardTitle}</Text>
                    </View>
                    <Text style={s.ball}>{isCompleted ? '🏆' : '⚽'}</Text>
                  </View>

                  {item.status === 'OPEN' ? (
                    <View style={s.timerBox}>
                      <Text style={s.timerLabel}>⏱ TIEMPO RESTANTE</Text>
                      <Text style={s.timerValue}>{countdownText(secondsLeft)}</Text>
                    </View>
                  ) : null}

                  {isMatched && item.opponent_club ? (
                    <Text style={s.matchup}>{item.creator_club} vs {item.opponent_club}</Text>
                  ) : null}

                  {item.room_access && isMatched ? (
                    <View style={s.accessBox}>
                      <Text style={s.accessTitle}>DATOS PARA ENTRAR A LA CANCHA</Text>
                      <Text style={s.accessText}>{openRoomText(item.room_access)}</Text>
                    </View>
                  ) : null}

                  {isCompleted && item.result ? (
                    <View style={s.resultBox}>
                      <Text style={s.resultLabel}>MARCADOR CONFIRMADO POR EL BOT</Text>
                      <View style={s.resultRow}>
                        <Text style={s.resultTeam}>{item.result.home_team}</Text>
                        <Text style={s.resultScore}>{item.result.home_goals} – {item.result.away_goals}</Text>
                        <Text style={[s.resultTeam, s.resultTeamRight]}>{item.result.away_team}</Text>
                      </View>
                    </View>
                  ) : null}

                  {isCompleted && !item.result ? (
                    <View style={s.resultBox}>
                      <Text style={s.resultLabel}>RESULTADO REGISTRADO</Text>
                      <Text style={s.resultPending}>El partido ya fue reconocido como finalizado.</Text>
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

                  {isMatched && item.is_owner ? (
                    <Pressable disabled={busyId === item.id} style={[s.danger, busyId === item.id && s.disabled]} onPress={() => cancel(item)}>
                      <Text style={s.dangerText}>CERRAR / CANCELAR PARTIDO</Text>
                    </Pressable>
                  ) : null}
                </View>
              );
            })}
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
  activeNotice: { backgroundColor: 'rgba(7,27,18,0.93)', borderWidth: 1, borderColor: '#285d40', borderRadius: 16, padding: 13 },
  activeNoticeTitle: { color: C.green, fontSize: 10, fontWeight: '900', letterSpacing: 0.8 },
  activeNoticeText: { color: C.white, fontSize: 11, lineHeight: 16, marginTop: 5 },
  primary: { minHeight: 50, borderRadius: 14, alignItems: 'center', justifyContent: 'center', backgroundColor: C.blue },
  primarySmall: { minHeight: 44, borderRadius: 12, alignItems: 'center', justifyContent: 'center', backgroundColor: C.blue, paddingHorizontal: 14 },
  primaryText: { color: C.white, fontSize: 10, fontWeight: '900', letterSpacing: 0.7 },
  formCard: { backgroundColor: C.panel2, borderWidth: 1, borderColor: C.blue, borderRadius: 18, padding: 15 },
  formTitle: { color: C.white, fontSize: 17, fontWeight: '900' },
  formHint: { color: C.orange, fontSize: 10.5, lineHeight: 15, marginTop: 6 },
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
  completedCard: { borderColor: '#9b7b2c', backgroundColor: 'rgba(28,22,7,0.96)' },
  cardHeader: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  cardEyebrow: { color: C.green, fontSize: 9, fontWeight: '900', letterSpacing: 1.2 },
  completedEyebrow: { color: '#ffd66f' },
  cardTitle: { color: C.white, fontSize: 18, lineHeight: 23, fontWeight: '900', marginTop: 5 },
  ball: { fontSize: 28 },
  timerBox: { marginTop: 12, minHeight: 58, borderRadius: 14, borderWidth: 1, borderColor: '#285d82', backgroundColor: 'rgba(5,20,31,0.92)', paddingHorizontal: 13, paddingVertical: 9, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  timerLabel: { color: C.blueSoft, fontSize: 9, fontWeight: '900', letterSpacing: 0.9 },
  timerValue: { color: C.white, fontSize: 22, fontWeight: '900', fontVariant: ['tabular-nums'] },
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
  resultBox: { borderWidth: 1, borderColor: '#9b7b2c', backgroundColor: 'rgba(20,15,4,0.94)', borderRadius: 16, padding: 13, marginTop: 13 },
  resultLabel: { color: '#ffd66f', fontSize: 8.5, fontWeight: '900', letterSpacing: 1 },
  resultRow: { marginTop: 11, flexDirection: 'row', alignItems: 'center' },
  resultTeam: { flex: 1, color: C.white, fontSize: 12, lineHeight: 16, fontWeight: '900' },
  resultTeamRight: { textAlign: 'right' },
  resultScore: { color: C.white, fontSize: 25, fontWeight: '900', paddingHorizontal: 10, fontVariant: ['tabular-nums'] },
  resultPending: { color: C.white, fontSize: 11, lineHeight: 16, marginTop: 7 },
});