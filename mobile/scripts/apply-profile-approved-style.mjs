import fs from 'node:fs';

const uiPath = new URL('../src/BotParityAppV2.tsx', import.meta.url);
let ui = fs.readFileSync(uiPath, 'utf8');
const marker = '// approved-profile-style applied';
if (ui.includes(marker)) process.exit(0);

const reactAnchorLegacy = "import React, { ReactNode, useCallback, useEffect, useMemo, useState } from 'react';";
const reactAnchorLayout = "import React, { ReactNode, useCallback, useEffect, useLayoutEffect, useMemo, useState } from 'react';";
if (!ui.includes("Shield, Settings, LogOut")) {
  const reactAnchor = ui.includes(reactAnchorLayout) ? reactAnchorLayout : reactAnchorLegacy;
  if (!ui.includes(reactAnchor)) throw new Error('Perfil aprobado: import React no encontrado');
  ui = ui.replace(
    reactAnchor,
    reactAnchor + "\nimport { Shield, Settings, LogOut, ChevronRight, CheckCircle2, Crown, UserRound } from 'lucide-react-native';\nimport { SvgUri } from 'react-native-svg';"
  );
}

const start = ui.indexOf('  const profileScreen = (');
let end = ui.indexOf('\n  const embeddedScreenTitle =', start);
if (end < 0) end = ui.indexOf('\n  const screenBackground = (() => {', start);
if (start < 0 || end < 0) throw new Error('Perfil aprobado: bloque profileScreen no encontrado');

const profile = String.raw`  const profileScreen = (
    <ScrollView
      contentContainerStyle={[s.content, s.profileApprovedContent]}
      refreshControl={refreshControl}
      keyboardShouldPersistTaps="handled"
      showsVerticalScrollIndicator={false}
    >
      <View style={s.profileApprovedTitleBlock}>
        <Text style={s.profileApprovedEyebrow}>PERFIL</Text>
        <Text style={s.profileApprovedTitle}>Perfil</Text>
        <Text style={s.profileApprovedSubtitle}>Cuenta, club y vinculación con Discord.</Text>
      </View>

      {profile ? (
        <>
          <View style={s.profileApprovedHero}>
            <View pointerEvents="none" style={s.profileApprovedHeroGlow} />
            <View style={s.profileApprovedAvatarRing}>
              {profile.user.avatar_url ? (
                <Image source={{ uri: profile.user.avatar_url }} style={s.profileApprovedAvatar} resizeMode="cover" />
              ) : (
                <View style={s.profileApprovedAvatarFallback}>
                  <UserRound size={43} color="#8FD1FF" strokeWidth={1.8} />
                </View>
              )}
            </View>
            <View style={s.profileApprovedHeroCopy}>
              <Text numberOfLines={1} style={s.profileApprovedAccountName}>
                {profile.user.global_name || profile.user.username || profile.user.id}
              </Text>
              <View style={s.profileApprovedLinkedRow}>
                <CheckCircle2 size={17} color="#2EA8FF" strokeWidth={2.4} />
                <Text style={s.profileApprovedLinkedText}>Cuenta vinculada</Text>
              </View>
              <View style={s.profileApprovedClubRow}>
                {profile.club ? <ClubBadge club={profile.club} size={31} /> : null}
                <Text numberOfLines={1} style={s.profileApprovedClubText}>{profile.club || 'Staff / sin club'}</Text>
              </View>
              {(profile.user.global_name || profile.user.username) ? (
                <Text numberOfLines={1} style={s.profileApprovedDiscordId}>Discord ID · {profile.user.id}</Text>
              ) : null}
            </View>
          </View>

          <Pressable onPress={() => openScreen('club')} style={({ pressed }) => [s.profileApprovedTile, pressed && s.profileApprovedPressed]}>
            <View style={s.profileApprovedTileIcon}><Shield size={31} color="#DDF4FF" strokeWidth={2} /></View>
            <View style={s.profileApprovedTileCopy}>
              <Text style={s.profileApprovedTileTitle}>Mi Club</Text>
              <Text numberOfLines={1} style={s.profileApprovedTileSubtitle}>{profile.club || 'Sin club asignado'}</Text>
            </View>
            <View style={s.profileApprovedArrow}><ChevronRight size={24} color="#2EA8FF" strokeWidth={2.5} /></View>
          </Pressable>

          <Pressable
            onPress={() => Alert.alert('Cuenta de Discord', (profile.user.global_name || profile.user.username || 'Cuenta vinculada') + '\\nID: ' + profile.user.id)}
            style={({ pressed }) => [s.profileApprovedTile, pressed && s.profileApprovedPressed]}
          >
            <View style={s.profileApprovedTileIcon}>
              <SvgUri width={31} height={31} uri="https://cdn.simpleicons.org/discord/FFFFFF" />
            </View>
            <View style={s.profileApprovedTileCopy}>
              <Text style={s.profileApprovedTileTitle}>Cuenta de Discord</Text>
              <Text numberOfLines={1} style={s.profileApprovedTileSubtitle}>{profile.user.id}</Text>
            </View>
            <View style={s.profileApprovedArrow}><ChevronRight size={24} color="#2EA8FF" strokeWidth={2.5} /></View>
          </Pressable>

          {profile.is_staff ? (
            <>
              <View style={s.profileApprovedSectionRow}>
                <Text style={s.profileApprovedSectionTitle}>ADMINISTRACIÓN</Text>
                <View style={s.profileApprovedAdminPill}>
                  <Crown size={13} color="#42B9FF" strokeWidth={2.2} />
                  <Text style={s.profileApprovedAdminPillText}>SOLO ADMIN</Text>
                </View>
              </View>
              <Pressable onPress={() => openScreen('admin')} style={({ pressed }) => [s.profileApprovedTile, pressed && s.profileApprovedPressed]}>
                <View style={s.profileApprovedTileIcon}><Settings size={31} color="#DDF4FF" strokeWidth={2} /></View>
                <View style={s.profileApprovedTileCopy}>
                  <Text style={s.profileApprovedTileTitle}>Panel Staff</Text>
                  <Text style={s.profileApprovedTileSubtitle}>Mercado, planteles, economía y gestión interna.</Text>
                </View>
                <View style={s.profileApprovedArrow}><ChevronRight size={24} color="#2EA8FF" strokeWidth={2.5} /></View>
              </Pressable>
            </>
          ) : null}

          <Pressable onPress={logout} style={({ pressed }) => [s.profileApprovedTile, s.profileApprovedLogoutTile, pressed && s.profileApprovedPressed]}>
            <View style={[s.profileApprovedTileIcon, s.profileApprovedLogoutIcon]}><LogOut size={31} color="#FF7383" strokeWidth={2.1} /></View>
            <View style={s.profileApprovedTileCopy}>
              <Text style={s.profileApprovedLogoutTitle}>Cerrar sesión</Text>
              <Text style={s.profileApprovedTileSubtitle}>Desvincular esta sesión del dispositivo.</Text>
            </View>
            <View style={[s.profileApprovedArrow, s.profileApprovedLogoutArrow]}><ChevronRight size={24} color="#FF7383" strokeWidth={2.5} /></View>
          </Pressable>
        </>
      ) : (
        <View style={s.profileApprovedLinkCard}>
          <View style={s.profileApprovedTileIcon}><SvgUri width={32} height={32} uri="https://cdn.simpleicons.org/discord/FFFFFF" /></View>
          <Text style={s.profileApprovedTileTitle}>Vincular Discord</Text>
          <Text style={s.profileApprovedLinkHelp}>En Discord abrí el menú principal y tocá “Vincular con la app”. Ingresá acá el código privado de 8 caracteres.</Text>
          <TextInput
            style={[s.input, s.codeInput]}
            value={pairCode}
            onChangeText={(value) => setPairCode(value.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 8))}
            maxLength={8}
            autoCapitalize="characters"
            placeholder="XXXXXXXX"
            placeholderTextColor="#657382"
          />
          <Button label={busy ? 'VINCULANDO…' : 'VINCULAR DISCORD'} onPress={pair} disabled={busy} />
        </View>
      )}
    </ScrollView>
  );`;

ui = ui.slice(0, start) + profile + ui.slice(end);

const sStart = ui.indexOf('const s = StyleSheet.create({');
const stylePos = sStart < 0 ? -1 : ui.indexOf('\n});', sStart);
if (stylePos < 0) throw new Error('Perfil aprobado: cierre de s StyleSheet no encontrado');

const styles = String.raw`
  profileApprovedContent: { paddingTop: 18, paddingHorizontal: 14, paddingBottom: 34, gap: 12 },
  profileApprovedTitleBlock: { marginBottom: 6 },
  profileApprovedEyebrow: { color: '#53B8F5', fontSize: 10, lineHeight: 13, fontWeight: '900', letterSpacing: 2.1 },
  profileApprovedTitle: { color: '#F7FBFF', fontSize: 29, lineHeight: 34, fontWeight: '900', marginTop: 5 },
  profileApprovedSubtitle: { color: '#8FA3B3', fontSize: 13, lineHeight: 18, marginTop: 3 },

  profileApprovedHero: { minHeight: 150, borderRadius: 24, borderWidth: 1.4, borderColor: '#2EA8FF', backgroundColor: '#081C2B', padding: 16, flexDirection: 'row', alignItems: 'center', overflow: 'hidden' },
  profileApprovedHeroGlow: { position: 'absolute', right: -70, top: -60, width: 220, height: 220, borderRadius: 110, backgroundColor: 'rgba(37,137,255,0.11)' },
  profileApprovedAvatarRing: { width: 98, height: 98, borderRadius: 49, borderWidth: 3, borderColor: '#26ABFF', backgroundColor: '#07131F', padding: 4, shadowColor: '#2EA8FF', shadowOpacity: 0.42, shadowRadius: 13, elevation: 4 },
  profileApprovedAvatar: { width: '100%', height: '100%', borderRadius: 44 },
  profileApprovedAvatarFallback: { flex: 1, borderRadius: 44, alignItems: 'center', justifyContent: 'center', backgroundColor: '#0B2233' },
  profileApprovedHeroCopy: { flex: 1, minWidth: 0, marginLeft: 16 },
  profileApprovedAccountName: { color: '#F7FBFF', fontSize: 19, lineHeight: 23, fontWeight: '900' },
  profileApprovedLinkedRow: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 7 },
  profileApprovedLinkedText: { color: '#42B9FF', fontSize: 12, fontWeight: '900' },
  profileApprovedClubRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 8 },
  profileApprovedClubText: { flex: 1, color: '#BAC8D3', fontSize: 13.5 },
  profileApprovedDiscordId: { color: '#627A8C', fontSize: 9.5, marginTop: 7 },

  profileApprovedTile: { minHeight: 92, borderRadius: 20, borderWidth: 1, borderColor: '#24577A', backgroundColor: '#0B2233', paddingHorizontal: 13, paddingVertical: 12, flexDirection: 'row', alignItems: 'center', overflow: 'hidden' },
  profileApprovedPressed: { opacity: 0.72, transform: [{ scale: 0.992 }] },
  profileApprovedTileIcon: { width: 58, height: 58, borderRadius: 17, borderWidth: 1.2, borderColor: '#288BCE', backgroundColor: '#09243A', alignItems: 'center', justifyContent: 'center' },
  profileApprovedTileCopy: { flex: 1, minWidth: 0, marginLeft: 13 },
  profileApprovedTileTitle: { color: '#F4F8FB', fontSize: 18, lineHeight: 21, fontWeight: '900' },
  profileApprovedTileSubtitle: { color: '#91A5B4', fontSize: 12, lineHeight: 17, marginTop: 5 },
  profileApprovedArrow: { width: 42, height: 42, borderRadius: 21, borderWidth: 1.2, borderColor: '#258ACB', backgroundColor: '#081B2A', alignItems: 'center', justifyContent: 'center', marginLeft: 9 },

  profileApprovedSectionRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 4, marginBottom: -2 },
  profileApprovedSectionTitle: { color: '#82BCE2', fontSize: 10, fontWeight: '900', letterSpacing: 1.9 },
  profileApprovedAdminPill: { flexDirection: 'row', alignItems: 'center', gap: 5, borderRadius: 999, borderWidth: 1, borderColor: '#2779A9', paddingHorizontal: 9, paddingVertical: 5, backgroundColor: 'rgba(5,25,39,0.76)' },
  profileApprovedAdminPillText: { color: '#42B9FF', fontSize: 8.5, fontWeight: '900', letterSpacing: 0.8 },

  profileApprovedLogoutTile: { borderColor: '#A73848', backgroundColor: '#2A1018' },
  profileApprovedLogoutIcon: { borderColor: '#C54756', backgroundColor: '#3A121C' },
  profileApprovedLogoutArrow: { borderColor: '#B63D4D', backgroundColor: '#281017' },
  profileApprovedLogoutTitle: { color: '#FF7180', fontSize: 18, lineHeight: 21, fontWeight: '900' },

  profileApprovedLinkCard: { borderRadius: 22, borderWidth: 1, borderColor: '#24577A', backgroundColor: '#0B2233', padding: 16, gap: 12 },
  profileApprovedLinkHelp: { color: '#91A5B4', fontSize: 12, lineHeight: 18 },
`;

let beforeStyles = ui.slice(0, stylePos);
if (!beforeStyles.trimEnd().endsWith(',')) beforeStyles = beforeStyles.trimEnd() + ',\n';
ui = beforeStyles + styles + ui.slice(stylePos);
ui += '\n' + marker + '\n';
fs.writeFileSync(uiPath, ui);
console.log('AJPA UI Lab: perfil aprobado aplicado con avatar real e iconografía de internet.');
