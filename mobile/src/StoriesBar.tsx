import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Animated,
  Image,
  Modal,
  Pressable,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import * as ImagePicker from 'expo-image-picker';

import { ClubBadge, getClubTheme } from './teamBadges';
import {
  StoryItem,
  createStory,
  deleteStory,
  fetchStories,
  markStoryViewed,
} from './storiesApi';

type StoryGroup = {
  team: string;
  stories: StoryItem[];
  unseen: boolean;
};

type Props = {
  authenticated: boolean;
  ownTeam: string | null | undefined;
};

const C = {
  white: '#f7fbff',
  muted: '#9aa8b4',
  blue: '#2d92ff',
  panel: 'rgba(5,13,21,0.90)',
  border: '#263b4d',
  grayRing: '#53616e',
  black: '#000000',
  red: '#ff6670',
};

const storyError = (error: unknown) =>
  error instanceof Error ? error.message : 'No se pudo completar la operación.';

const relativeTime = (timestamp: number) => {
  const seconds = Math.max(0, Math.floor(Date.now() / 1000 - timestamp));
  if (seconds < 60) return 'ahora';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `hace ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  return `hace ${hours} h`;
};

export default function StoriesBar({ authenticated, ownTeam }: Props) {
  const [stories, setStories] = useState<StoryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [composerOpen, setComposerOpen] = useState(false);
  const [draftImage, setDraftImage] = useState<string | null>(null);
  const [caption, setCaption] = useState('');
  const [publishing, setPublishing] = useState(false);
  const [viewerTeamIndex, setViewerTeamIndex] = useState<number | null>(null);
  const [viewerStoryIndex, setViewerStoryIndex] = useState(0);
  const progress = useRef(new Animated.Value(0)).current;

  const load = useCallback(async (quiet = false) => {
    if (!authenticated) {
      setStories([]);
      return;
    }
    if (!quiet) setLoading(true);
    try {
      const result = await fetchStories();
      setStories(result.stories ?? []);
    } catch (error) {
      if (!quiet) console.log('AJPA stories load:', storyError(error));
    } finally {
      if (!quiet) setLoading(false);
    }
  }, [authenticated]);

  useEffect(() => {
    void load();
    if (!authenticated) return;
    const timer = setInterval(() => void load(true), 45000);
    return () => clearInterval(timer);
  }, [authenticated, load]);

  const groups = useMemo<StoryGroup[]>(() => {
    const map = new Map<string, StoryItem[]>();
    for (const story of stories) {
      const list = map.get(story.team) ?? [];
      list.push(story);
      map.set(story.team, list);
    }
    const result = [...map.entries()].map(([team, teamStories]) => ({
      team,
      stories: teamStories.sort((a, b) => a.created_at - b.created_at || a.id - b.id),
      unseen: teamStories.some((story) => !story.viewed),
    }));
    result.sort((a, b) => {
      const aOwn = !!ownTeam && a.team.toLowerCase() === ownTeam.toLowerCase();
      const bOwn = !!ownTeam && b.team.toLowerCase() === ownTeam.toLowerCase();
      if (aOwn !== bOwn) return aOwn ? -1 : 1;
      if (a.unseen !== b.unseen) return a.unseen ? -1 : 1;
      return a.team.localeCompare(b.team);
    });
    return result;
  }, [stories, ownTeam]);

  const viewerGroup = viewerTeamIndex === null ? null : groups[viewerTeamIndex] ?? null;
  const viewerStory = viewerGroup?.stories[viewerStoryIndex] ?? null;

  const markViewedLocal = useCallback((story: StoryItem | null) => {
    if (!story || story.viewed) return;
    setStories((current) => current.map((item) => item.id === story.id ? { ...item, viewed: true } : item));
    void markStoryViewed(story.id).catch(() => undefined);
  }, []);

  const closeViewer = useCallback(() => {
    progress.stopAnimation();
    progress.setValue(0);
    setViewerTeamIndex(null);
    setViewerStoryIndex(0);
  }, [progress]);

  const goNext = useCallback(() => {
    if (viewerTeamIndex === null || !viewerGroup) return;
    if (viewerStoryIndex + 1 < viewerGroup.stories.length) {
      setViewerStoryIndex((value) => value + 1);
      return;
    }
    if (viewerTeamIndex + 1 < groups.length) {
      setViewerTeamIndex((value) => (value === null ? null : value + 1));
      setViewerStoryIndex(0);
      return;
    }
    closeViewer();
  }, [viewerTeamIndex, viewerStoryIndex, viewerGroup, groups.length, closeViewer]);

  const goPrevious = useCallback(() => {
    if (viewerTeamIndex === null || !viewerGroup) return;
    if (viewerStoryIndex > 0) {
      setViewerStoryIndex((value) => Math.max(0, value - 1));
      return;
    }
    if (viewerTeamIndex > 0) {
      const previous = groups[viewerTeamIndex - 1];
      setViewerTeamIndex(viewerTeamIndex - 1);
      setViewerStoryIndex(Math.max(0, previous.stories.length - 1));
    }
  }, [viewerTeamIndex, viewerStoryIndex, viewerGroup, groups]);

  useEffect(() => {
    if (!viewerStory) return;
    markViewedLocal(viewerStory);
    progress.stopAnimation();
    progress.setValue(0);
    const animation = Animated.timing(progress, {
      toValue: 1,
      duration: 5500,
      useNativeDriver: false,
    });
    animation.start(({ finished }) => {
      if (finished) goNext();
    });
    return () => animation.stop();
  }, [viewerStory?.id, markViewedLocal, progress, goNext]);

  const openGroup = (team: string) => {
    const index = groups.findIndex((group) => group.team === team);
    if (index < 0) return;
    const firstUnseen = groups[index].stories.findIndex((story) => !story.viewed);
    setViewerTeamIndex(index);
    setViewerStoryIndex(firstUnseen >= 0 ? firstUnseen : 0);
  };

  const pickImage = async () => {
    if (!ownTeam) {
      Alert.alert('Historias AJPA', 'Necesitás un club asignado para publicar una historia.');
      return;
    }
    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) {
      Alert.alert('Permiso necesario', 'Permití el acceso a tus fotos para subir una historia.');
      return;
    }
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      allowsEditing: true,
      aspect: [9, 16],
      quality: 0.5,
      base64: true,
    });
    if (result.canceled || !result.assets[0]?.base64) return;
    const asset = result.assets[0];
    const mime = asset.mimeType && ['image/jpeg', 'image/png', 'image/webp'].includes(asset.mimeType)
      ? asset.mimeType
      : 'image/jpeg';
    setDraftImage(`data:${mime};base64,${asset.base64}`);
    setCaption('');
    setComposerOpen(true);
  };

  const publish = async () => {
    if (!draftImage || publishing) return;
    setPublishing(true);
    try {
      await createStory(draftImage, caption.trim());
      setComposerOpen(false);
      setDraftImage(null);
      setCaption('');
      await load(true);
      Alert.alert('Historia publicada', 'Tu historia estará visible durante 24 horas.');
    } catch (error) {
      Alert.alert('No se publicó', storyError(error));
    } finally {
      setPublishing(false);
    }
  };

  const removeCurrent = () => {
    if (!viewerStory?.owner) return;
    Alert.alert('Eliminar historia', '¿Querés eliminar esta historia ahora?', [
      { text: 'Cancelar', style: 'cancel' },
      {
        text: 'ELIMINAR',
        style: 'destructive',
        onPress: async () => {
          try {
            await deleteStory(viewerStory.id);
            closeViewer();
            await load(true);
          } catch (error) {
            Alert.alert('Historias AJPA', storyError(error));
          }
        },
      },
    ]);
  };

  if (!authenticated) return null;

  const ownGroup = ownTeam ? groups.find((group) => group.team.toLowerCase() === ownTeam.toLowerCase()) : undefined;

  return (
    <>
      <View style={s.section}>
        <View style={s.sectionHeader}>
          <Text style={s.sectionTitle}>HISTORIAS</Text>
          {loading ? <ActivityIndicator size="small" color={C.blue} /> : null}
        </View>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.row}>
          {ownTeam ? (
            <View style={s.storySlot}>
              <Pressable
                onPress={() => ownGroup ? openGroup(ownGroup.team) : void pickImage()}
                style={[s.ring, { borderColor: ownGroup?.unseen ? getClubTheme(ownTeam).primary : C.grayRing }]}
              >
                <View style={s.badgeCircle}>
                  <ClubBadge club={ownTeam} size={54} />
                </View>
              </Pressable>
              <Pressable onPress={() => void pickImage()} style={s.plusBadge} hitSlop={8}>
                <Text style={s.plusText}>＋</Text>
              </Pressable>
              <Text style={s.storyName} numberOfLines={1}>Tu historia</Text>
            </View>
          ) : null}

          {groups
            .filter((group) => !ownTeam || group.team.toLowerCase() !== ownTeam.toLowerCase())
            .map((group) => {
              const theme = getClubTheme(group.team);
              return (
                <View key={group.team} style={s.storySlot}>
                  <Pressable
                    onPress={() => openGroup(group.team)}
                    style={[s.ring, { borderColor: group.unseen ? theme.primary : C.grayRing }]}
                  >
                    <View style={s.badgeCircle}>
                      <ClubBadge club={group.team} size={54} />
                    </View>
                  </Pressable>
                  <Text style={[s.storyName, group.unseen && s.storyNameUnseen]} numberOfLines={1}>{group.team}</Text>
                </View>
              );
            })}
        </ScrollView>
      </View>

      <Modal visible={composerOpen} animationType="slide" onRequestClose={() => !publishing && setComposerOpen(false)}>
        <SafeAreaView style={s.composer}>
          <View style={s.composerTop}>
            <Pressable disabled={publishing} onPress={() => setComposerOpen(false)}><Text style={s.topAction}>CANCELAR</Text></Pressable>
            <View style={s.composerIdentity}>
              <ClubBadge club={ownTeam} size={30} />
              <Text style={s.composerTeam}>{ownTeam}</Text>
            </View>
            <Pressable disabled={publishing} onPress={() => void publish()}>
              <Text style={[s.topAction, s.publishAction, publishing && { opacity: 0.5 }]}>{publishing ? 'REVISANDO…' : 'PUBLICAR'}</Text>
            </Pressable>
          </View>
          {draftImage ? <Image source={{ uri: draftImage }} style={s.composerImage} resizeMode="contain" /> : null}
          <View style={s.captionBox}>
            <TextInput
              style={s.captionInput}
              value={caption}
              onChangeText={(value) => setCaption(value.slice(0, 250))}
              placeholder="Agregá un texto…"
              placeholderTextColor="#7c8790"
              maxLength={250}
              multiline
              editable={!publishing}
            />
            <Text style={s.counter}>{caption.length}/250</Text>
          </View>
          {publishing ? (
            <View style={s.reviewBanner}>
              <ActivityIndicator color={C.white} />
              <View style={{ flex: 1 }}>
                <Text style={s.reviewTitle}>Revisando contenido…</Text>
                <Text style={s.reviewText}>La foto y el texto deben aprobar el filtro antes de publicarse.</Text>
              </View>
            </View>
          ) : null}
        </SafeAreaView>
      </Modal>

      <Modal visible={viewerTeamIndex !== null} animationType="fade" onRequestClose={closeViewer}>
        <SafeAreaView style={s.viewer}>
          {viewerGroup && viewerStory ? (
            <>
              <View style={s.progressRow}>
                {viewerGroup.stories.map((story, index) => (
                  <View key={story.id} style={s.progressTrack}>
                    {index < viewerStoryIndex ? <View style={[s.progressFill, { width: '100%' }]} /> : null}
                    {index === viewerStoryIndex ? (
                      <Animated.View
                        style={[
                          s.progressFill,
                          { width: progress.interpolate({ inputRange: [0, 1], outputRange: ['0%', '100%'] }) },
                        ]}
                      />
                    ) : null}
                  </View>
                ))}
              </View>
              <View style={s.viewerHeader}>
                <ClubBadge club={viewerGroup.team} size={38} />
                <View style={{ flex: 1 }}>
                  <Text style={s.viewerTeam}>{viewerGroup.team}</Text>
                  <Text style={s.viewerTime}>{relativeTime(viewerStory.created_at)}</Text>
                </View>
                {viewerStory.owner ? <Pressable onPress={removeCurrent} style={s.viewerAction}><Text style={s.viewerActionText}>•••</Text></Pressable> : null}
                <Pressable onPress={closeViewer} style={s.viewerAction}><Text style={s.close}>×</Text></Pressable>
              </View>
              <Image source={{ uri: viewerStory.image_data_url }} style={s.viewerImage} resizeMode="contain" />
              <View style={s.tapLayer} pointerEvents="box-none">
                <Pressable style={s.tapHalf} onPress={goPrevious} />
                <Pressable style={s.tapHalf} onPress={goNext} />
              </View>
              {viewerStory.caption ? (
                <View style={s.viewerCaptionWrap} pointerEvents="none">
                  <Text style={s.viewerCaption}>{viewerStory.caption}</Text>
                </View>
              ) : null}
            </>
          ) : null}
        </SafeAreaView>
      </Modal>
    </>
  );
}

const s = StyleSheet.create({
  section: { marginBottom: 2, marginHorizontal: -16, paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: 'rgba(38,59,77,0.6)' },
  sectionHeader: { minHeight: 20, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 16, marginBottom: 6 },
  sectionTitle: { color: C.muted, fontSize: 9, fontWeight: '900', letterSpacing: 1.5 },
  row: { paddingHorizontal: 12, paddingBottom: 3, gap: 8 },
  storySlot: { width: 76, alignItems: 'center', position: 'relative' },
  ring: { width: 68, height: 68, borderRadius: 34, borderWidth: 2.5, alignItems: 'center', justifyContent: 'center', padding: 3 },
  badgeCircle: { width: 58, height: 58, borderRadius: 29, backgroundColor: '#07111a', alignItems: 'center', justifyContent: 'center', overflow: 'hidden' },
  plusBadge: { position: 'absolute', right: 4, top: 45, width: 23, height: 23, borderRadius: 12, backgroundColor: C.blue, borderWidth: 2, borderColor: '#08131d', alignItems: 'center', justifyContent: 'center' },
  plusText: { color: C.white, fontSize: 17, fontWeight: '900', lineHeight: 18 },
  storyName: { width: 74, color: C.muted, fontSize: 9.5, textAlign: 'center', marginTop: 5 },
  storyNameUnseen: { color: C.white, fontWeight: '800' },
  composer: { flex: 1, backgroundColor: '#020609' },
  composerTop: { height: 62, paddingHorizontal: 14, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', borderBottomWidth: 1, borderBottomColor: '#1d2c38' },
  composerIdentity: { maxWidth: '46%', flexDirection: 'row', alignItems: 'center', gap: 8 },
  composerTeam: { color: C.white, fontSize: 12, fontWeight: '900', flexShrink: 1 },
  topAction: { color: C.muted, fontSize: 10, fontWeight: '900', letterSpacing: 0.7 },
  publishAction: { color: '#63adff' },
  composerImage: { flex: 1, width: '100%', backgroundColor: C.black },
  captionBox: { padding: 12, borderTopWidth: 1, borderTopColor: '#1d2c38', backgroundColor: C.panel },
  captionInput: { minHeight: 58, maxHeight: 100, color: C.white, fontSize: 15, textAlignVertical: 'top' },
  counter: { color: '#71808c', fontSize: 9, alignSelf: 'flex-end' },
  reviewBanner: { flexDirection: 'row', gap: 12, alignItems: 'center', padding: 14, backgroundColor: '#123c62' },
  reviewTitle: { color: C.white, fontWeight: '900', fontSize: 12 },
  reviewText: { color: '#c7d8e8', fontSize: 10.5, lineHeight: 15, marginTop: 2 },
  viewer: { flex: 1, backgroundColor: C.black },
  progressRow: { position: 'absolute', zIndex: 20, top: 9, left: 8, right: 8, height: 3, flexDirection: 'row', gap: 4 },
  progressTrack: { flex: 1, height: 3, borderRadius: 2, backgroundColor: 'rgba(255,255,255,0.28)', overflow: 'hidden' },
  progressFill: { height: 3, backgroundColor: C.white },
  viewerHeader: { position: 'absolute', zIndex: 20, top: 22, left: 12, right: 8, height: 50, flexDirection: 'row', alignItems: 'center', gap: 9 },
  viewerTeam: { color: C.white, fontSize: 12.5, fontWeight: '900' },
  viewerTime: { color: '#b7c0c8', fontSize: 10, marginTop: 1 },
  viewerAction: { minWidth: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  viewerActionText: { color: C.white, fontSize: 15, fontWeight: '900', letterSpacing: 2 },
  close: { color: C.white, fontSize: 32, fontWeight: '300', lineHeight: 35 },
  viewerImage: { flex: 1, width: '100%', backgroundColor: C.black },
  tapLayer: { position: 'absolute', top: 82, left: 0, right: 0, bottom: 0, zIndex: 10, flexDirection: 'row' },
  tapHalf: { flex: 1 },
  viewerCaptionWrap: { position: 'absolute', zIndex: 21, left: 20, right: 20, bottom: 40, alignItems: 'center' },
  viewerCaption: { color: C.white, fontSize: 16, fontWeight: '700', textAlign: 'center', lineHeight: 22, backgroundColor: 'rgba(0,0,0,0.52)', paddingHorizontal: 10, paddingVertical: 7, borderRadius: 10 },
});
