import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Image,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import * as AuthSession from 'expo-auth-session';
import * as SecureStore from 'expo-secure-store';
import * as WebBrowser from 'expo-web-browser';

import LiveApp from './LiveApp';
import { ApiError, MeProfile, RosterPlayer, fetchMe, fetchRoster } from './api';

WebBrowser.maybeCompleteAuthSession();

const CLIENT_ID = (process.env.EXPO_PUBLIC_DISCORD_CLIENT_ID ?? '1541608838032265238').trim();
export const DISCORD_REDIRECT_URI = `discord-${CLIENT_ID}:/authorize/callback`;
const ACCESS_TOKEN_KEY = 'ajpa.discord.access_token';
const REFRESH_TOKEN_KEY = 'ajpa.discord.refresh_token';

const discovery: AuthSession.DiscoveryDocument = {
  authorizationEndpoint: 'https://discord.com/oauth2/authorize',
  tokenEndpoint: 'https://discord.com/api/oauth2/token',
  revocationEndpoint: 'https://discord.com/api/oauth2/token/revoke',
};

const money = (value: number | null | undefined) => {
  if (value === null || value === undefined) return '—';
  return `$${Math.round(value).toLocaleString('es-AR')}`;
};

async function saveTokens(token: AuthSession.TokenResponse) {
  await SecureStore.setItemAsync(ACCESS_TOKEN_KEY, token.accessToken);
  if (token.refreshToken) {
    await SecureStore.setItemAsync(REFRESH_TOKEN_KEY, token.refreshToken);
  }
}

async function clearTokens() {
  await Promise.all([
    SecureStore.deleteItemAsync(ACCESS_TOKEN_KEY),
    SecureStore.deleteItemAsync(REFRESH_TOKEN_KEY),
  ]);
}

function avatarUrl(profile: MeProfile | null) {
  if (!profile?.user.avatar) return null;
  return `https://cdn.discordapp.com/avatars/${profile.user.id}/${profile.user.avatar}.png?size=128`;
}

export default function AuthApp() {
  const [profile, setProfile] = useState<MeProfile | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [roster, setRoster] = useState<RosterPlayer[]>([]);
  const [loading, setLoading] = useState(true);
  const [authBusy, setAuthBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showLeague, setShowLeague] = useState(false);

  const [request, response, promptAsync] = AuthSession.useAuthRequest(
    {
      clientId: CLIENT_ID,
      redirectUri: DISCORD_REDIRECT_URI,
      responseType: AuthSession.ResponseType.Code,
      scopes: ['identify', 'guilds'],
      usePKCE: true,
      prompt: AuthSession.Prompt.Consent,
    },
    discovery,
  );

  const loadProfile = useCallback(async (token: string, allowRefresh = true) => {
    try {
      const me = await fetchMe(token);
      setAccessToken(token);
      setProfile(me);
      setError(null);
      return true;
    } catch (rawError) {
      const apiError = rawError as ApiError;
      if (allowRefresh && apiError?.status === 401) {
        const refreshToken = await SecureStore.getItemAsync(REFRESH_TOKEN_KEY);
        if (refreshToken) {
          try {
            const refreshed = await AuthSession.refreshAsync(
              { clientId: CLIENT_ID, refreshToken, scopes: ['identify', 'guilds'] },
              discovery,
            );
            await saveTokens(refreshed);
            return loadProfile(refreshed.accessToken, false);
          } catch {
            // Fall through and clear the stale session.
          }
        }
      }
      await clearTokens();
      setAccessToken(null);
      setProfile(null);
      setRoster([]);
      if (apiError?.status && apiError.status !== 401) {
        setError(apiError.message || 'No se pudo validar tu cuenta de Discord.');
      }
      return false;
    }
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const token = await SecureStore.getItemAsync(ACCESS_TOKEN_KEY);
        if (token) await loadProfile(token);
      } finally {
        setLoading(false);
      }
    })();
  }, [loadProfile]);

  useEffect(() => {
    if (response?.type !== 'success' || !response.params.code || !request?.codeVerifier) return;
    let cancelled = false;
    (async () => {
      setAuthBusy(true);
      setError(null);
      try {
        const token = await AuthSession.exchangeCodeAsync(
          {
            clientId: CLIENT_ID,
            code: response.params.code,
            redirectUri: DISCORD_REDIRECT_URI,
            scopes: ['identify', 'guilds'],
            extraParams: { code_verifier: request.codeVerifier! },
          },
          discovery,
        );
        await saveTokens(token);
        if (!cancelled) await loadProfile(token.accessToken, false);
      } catch (err) {
        if (!cancelled) {
          setError(
            'Discord no pudo completar el login. Revisá Public Client y el Redirect URI de la aplicación.',
          );
        }
      } finally {
        if (!cancelled) setAuthBusy(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [response, request, loadProfile]);

  useEffect(() => {
    if (!profile?.club) {
      setRoster([]);
      return;
    }
    let cancelled = false;
    fetchRoster(profile.club)
      .then((players) => {
        if (!cancelled) setRoster(players);
      })
      .catch(() => {
        if (!cancelled) setRoster([]);
      });
    return () => {
      cancelled = true;
    };
  }, [profile?.club]);

  const displayName = profile?.user.global_name || profile?.user.username || 'Discord';
  const avatar = useMemo(() => avatarUrl(profile), [profile]);

  const logout = useCallback(async () => {
    if (accessToken) {
      try {
        await AuthSession.revokeAsync(
          { clientId: CLIENT_ID, token: accessToken },
          discovery,
        );
      } catch {
        // Local logout still proceeds if Discord revocation is unavailable.
      }
    }
    await clearTokens();
    setProfile(null);
    setAccessToken(null);
    setRoster([]);
    setShowLeague(false);
    setError(null);
  }, [accessToken]);

  if (showLeague && profile) {
    return (
      <View style={styles.full}>
        <View style={styles.returnBar}>
          <Pressable onPress={() => setShowLeague(false)} style={styles.returnButton}>
            <Text style={styles.returnText}>‹ MI CLUB</Text>
          </Pressable>
          <Text style={styles.returnUser}>{displayName}</Text>
        </View>
        <View style={styles.liveContainer}>
          <LiveApp />
        </View>
      </View>
    );
  }

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" />
        <Text style={styles.muted}>Abriendo AJPA…</Text>
      </View>
    );
  }

  if (!profile) {
    return (
      <ScrollView contentContainerStyle={styles.loginScreen}>
        <View style={styles.brandMark}>
          <Text style={styles.brandMarkText}>AJPA</Text>
        </View>
        <Text style={styles.title}>Transfer Market</Text>
        <Text style={styles.subtitle}>
          Entrá con la misma cuenta de Discord que usás en la liga.
        </Text>
        <View style={styles.loginCard}>
          <Text style={styles.cardTitle}>Tu cuenta, tu club</Text>
          <Text style={styles.bodyText}>
            La app va a reconocer tu asignación real, presupuesto y plantel. Por ahora sigue en modo lectura.
          </Text>
          <Pressable
            disabled={!request || authBusy}
            onPress={() => promptAsync()}
            style={[styles.discordButton, (!request || authBusy) && styles.disabledButton]}
          >
            {authBusy ? <ActivityIndicator /> : <Text style={styles.discordButtonText}>ENTRAR CON DISCORD</Text>}
          </Pressable>
          {error ? <Text style={styles.errorText}>{error}</Text> : null}
        </View>
        <Text style={styles.securityText}>
          OAuth2 + PKCE · la contraseña de Discord nunca pasa por AJPA.
        </Text>
      </ScrollView>
    );
  }

  return (
    <ScrollView contentContainerStyle={styles.profileScreen}>
      <View style={styles.topRow}>
        <View style={styles.identityRow}>
          {avatar ? (
            <Image source={{ uri: avatar }} style={styles.avatar} />
          ) : (
            <View style={styles.avatarFallback}><Text style={styles.avatarFallbackText}>D</Text></View>
          )}
          <View style={styles.identityText}>
            <Text style={styles.eyebrow}>CUENTA DISCORD</Text>
            <Text style={styles.userName}>{displayName}</Text>
            <Text style={styles.userHandle}>@{profile.user.username}</Text>
          </View>
        </View>
        {profile.is_staff ? <View style={styles.staffPill}><Text style={styles.staffPillText}>STAFF</Text></View> : null}
      </View>

      {!profile.in_guild ? (
        <View style={styles.warningCard}>
          <Text style={styles.warningTitle}>Servidor AJPA no encontrado</Text>
          <Text style={styles.bodyText}>Esta cuenta de Discord no figura dentro del servidor configurado para la liga.</Text>
        </View>
      ) : !profile.club ? (
        <View style={styles.warningCard}>
          <Text style={styles.warningTitle}>{profile.is_staff ? 'Perfil Staff' : 'Sin club asignado'}</Text>
          <Text style={styles.bodyText}>
            {profile.is_staff
              ? 'Tu cuenta tiene permisos de administrador. Podés consultar la liga sin afiliarte a un equipo.'
              : 'Tu Discord está verificado, pero todavía no tiene un club vigente en el bot.'}
          </Text>
        </View>
      ) : (
        <>
          <View style={styles.clubHero}>
            <Text style={styles.eyebrow}>MI CLUB</Text>
            <Text style={styles.clubName}>{profile.club}</Text>
            <View style={styles.clubStats}>
              <View style={styles.statBox}>
                <Text style={styles.statLabel}>PRESUPUESTO</Text>
                <Text style={styles.statValue}>{money(profile.balance)}</Text>
              </View>
              <View style={styles.statBox}>
                <Text style={styles.statLabel}>PLANTEL</Text>
                <Text style={styles.statValue}>{profile.roster_count}/32</Text>
              </View>
            </View>
          </View>

          <Text style={styles.sectionTitle}>Plantel oficial</Text>
          {roster.length === 0 ? <Text style={styles.muted}>No hay jugadores para mostrar.</Text> : null}
          {roster.map((player) => (
            <View key={player.id ?? player.name} style={styles.playerCard}>
              <View style={styles.ovrBox}>
                <Text style={styles.ovrValue}>{player.ovr ?? '—'}</Text>
                <Text style={styles.ovrLabel}>OVR</Text>
              </View>
              <View style={styles.playerText}>
                <Text style={styles.playerName}>{player.name}</Text>
                <Text style={styles.muted}>{player.position || 'Sin posición'} · {player.code || 'SIN ID'}</Text>
              </View>
              <Text style={styles.playerValue}>{money(player.market_value)}</Text>
            </View>
          ))}
        </>
      )}

      <Pressable onPress={() => setShowLeague(true)} style={styles.secondaryButton}>
        <Text style={styles.secondaryButtonText}>EXPLORAR LIGA Y MERCADO</Text>
      </Pressable>
      <Pressable onPress={logout} style={styles.logoutButton}>
        <Text style={styles.logoutText}>Cerrar sesión</Text>
      </Pressable>
      {error ? <Text style={styles.errorText}>{error}</Text> : null}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  full: { flex: 1, backgroundColor: '#0c1712' },
  liveContainer: { flex: 1 },
  center: { flex: 1, backgroundColor: '#0c1712', alignItems: 'center', justifyContent: 'center', gap: 12 },
  muted: { color: '#8da398', fontSize: 12 },
  loginScreen: { flexGrow: 1, backgroundColor: '#0c1712', padding: 24, justifyContent: 'center', alignItems: 'center' },
  brandMark: { width: 88, height: 88, borderRadius: 24, backgroundColor: '#163b2a', borderWidth: 1, borderColor: '#2b6b48', alignItems: 'center', justifyContent: 'center' },
  brandMarkText: { color: '#8fe7ad', fontSize: 24, fontWeight: '900', letterSpacing: 2 },
  title: { color: '#f6fff8', fontSize: 31, fontWeight: '900', marginTop: 18 },
  subtitle: { color: '#91a79b', textAlign: 'center', fontSize: 14, lineHeight: 20, marginTop: 8, maxWidth: 320 },
  loginCard: { width: '100%', backgroundColor: '#111f18', borderWidth: 1, borderColor: '#21372b', borderRadius: 20, padding: 18, marginTop: 28 },
  cardTitle: { color: '#f6fff8', fontSize: 19, fontWeight: '900' },
  bodyText: { color: '#a7b9af', fontSize: 13, lineHeight: 19, marginTop: 7 },
  discordButton: { backgroundColor: '#5865F2', borderRadius: 14, minHeight: 52, alignItems: 'center', justifyContent: 'center', marginTop: 20 },
  disabledButton: { opacity: 0.55 },
  discordButtonText: { color: '#ffffff', fontWeight: '900', fontSize: 13, letterSpacing: 0.8 },
  errorText: { color: '#f0a1a1', fontSize: 12, lineHeight: 18, marginTop: 14, textAlign: 'center' },
  securityText: { color: '#60776b', fontSize: 11, textAlign: 'center', marginTop: 16 },
  profileScreen: { flexGrow: 1, backgroundColor: '#0c1712', padding: 16, paddingBottom: 32 },
  topRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 18 },
  identityRow: { flexDirection: 'row', alignItems: 'center', flex: 1 },
  identityText: { marginLeft: 12, flex: 1 },
  avatar: { width: 52, height: 52, borderRadius: 16 },
  avatarFallback: { width: 52, height: 52, borderRadius: 16, backgroundColor: '#193326', alignItems: 'center', justifyContent: 'center' },
  avatarFallbackText: { color: '#8eeaab', fontWeight: '900', fontSize: 18 },
  eyebrow: { color: '#5edc89', fontWeight: '900', fontSize: 10, letterSpacing: 1.7 },
  userName: { color: '#f6fff8', fontSize: 20, fontWeight: '900', marginTop: 2 },
  userHandle: { color: '#71877b', fontSize: 11, marginTop: 1 },
  staffPill: { backgroundColor: '#413515', borderWidth: 1, borderColor: '#746027', borderRadius: 999, paddingHorizontal: 10, paddingVertical: 6 },
  staffPillText: { color: '#f0d67e', fontSize: 9, fontWeight: '900', letterSpacing: 1 },
  warningCard: { backgroundColor: '#241f13', borderWidth: 1, borderColor: '#514522', borderRadius: 18, padding: 16, marginBottom: 16 },
  warningTitle: { color: '#f0d67e', fontSize: 17, fontWeight: '900' },
  clubHero: { backgroundColor: '#111f18', borderWidth: 1, borderColor: '#245038', borderRadius: 20, padding: 18 },
  clubName: { color: '#f6fff8', fontWeight: '900', fontSize: 26, marginTop: 4 },
  clubStats: { flexDirection: 'row', gap: 10, marginTop: 16 },
  statBox: { flex: 1, backgroundColor: '#0c1712', borderRadius: 14, padding: 12 },
  statLabel: { color: '#71877b', fontSize: 9, fontWeight: '900', letterSpacing: 1 },
  statValue: { color: '#f6fff8', fontSize: 17, fontWeight: '900', marginTop: 5 },
  sectionTitle: { color: '#f6fff8', fontWeight: '900', fontSize: 18, marginTop: 22, marginBottom: 10 },
  playerCard: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#111f18', borderWidth: 1, borderColor: '#21372b', borderRadius: 15, padding: 12, marginBottom: 8 },
  ovrBox: { width: 45, height: 45, borderRadius: 12, backgroundColor: '#193326', alignItems: 'center', justifyContent: 'center' },
  ovrValue: { color: '#8eeaab', fontSize: 17, fontWeight: '900', lineHeight: 19 },
  ovrLabel: { color: '#5f8f70', fontSize: 7, fontWeight: '900' },
  playerText: { flex: 1, marginLeft: 11 },
  playerName: { color: '#f6fff8', fontSize: 14, fontWeight: '800' },
  playerValue: { color: '#f6fff8', fontSize: 12, fontWeight: '900', marginLeft: 6 },
  secondaryButton: { backgroundColor: '#193326', borderWidth: 1, borderColor: '#2b6b48', borderRadius: 14, minHeight: 50, alignItems: 'center', justifyContent: 'center', marginTop: 18 },
  secondaryButtonText: { color: '#9ef0b9', fontWeight: '900', fontSize: 12, letterSpacing: 0.7 },
  logoutButton: { minHeight: 44, alignItems: 'center', justifyContent: 'center', marginTop: 8 },
  logoutText: { color: '#82998d', fontSize: 12, fontWeight: '700' },
  returnBar: { height: 42, backgroundColor: '#08110d', borderBottomWidth: 1, borderBottomColor: '#1d2d25', flexDirection: 'row', alignItems: 'center', paddingHorizontal: 12 },
  returnButton: { paddingVertical: 8, paddingRight: 12 },
  returnText: { color: '#59df88', fontSize: 11, fontWeight: '900', letterSpacing: 0.8 },
  returnUser: { color: '#71877b', fontSize: 10, marginLeft: 'auto' },
});
