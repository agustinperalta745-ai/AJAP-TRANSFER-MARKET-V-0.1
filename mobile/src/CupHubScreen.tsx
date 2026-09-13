import React, { useState } from 'react';
import { Image, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import CupCenterFab from './CupCenterFab';

type CompetitionKey = 'champions' | 'europa';

const CHAMPIONS_BANNER = require('../assets/trophies/champions-ajpa-banner.jpg');
const EUROPA_BANNER = require('../assets/trophies/europa-ajpa-banner.jpg');

const CUP_META: Record<CompetitionKey, { title: string; eyebrow: string; subtitle: string; accent: string; image: any }> = {
  champions: {
    title: 'Champions AJPA',
    eyebrow: 'MÁXIMA COPA',
    subtitle: 'Cuadro, cruces, resultados y camino al título.',
    accent: '#88b8ff',
    image: CHAMPIONS_BANNER,
  },
  europa: {
    title: 'Europa AJPA',
    eyebrow: 'COPA EUROPA',
    subtitle: 'Cuadro, cruces, resultados y equipos que bajan desde Champions.',
    accent: '#e7a15c',
    image: EUROPA_BANNER,
  },
};

function CupCard({ competition, onPress }: { competition: CompetitionKey; onPress: () => void }) {
  const meta = CUP_META[competition];
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [styles.card, { borderColor: `${meta.accent}88` }, pressed && styles.pressed]}
    >
      <View style={styles.bannerStage}>
        <Image source={meta.image} resizeMode="cover" fadeDuration={0} style={styles.banner} />
      </View>
      <View style={styles.copy}>
        <Text style={[styles.eyebrow, { color: meta.accent }]}>{meta.eyebrow}</Text>
        <Text style={styles.title}>{meta.title}</Text>
        <Text style={styles.subtitle}>{meta.subtitle}</Text>
        <View style={styles.openRow}>
          <Text style={styles.openLabel}>VER BRACKET Y RESULTADOS</Text>
          <Text style={[styles.chevron, { color: meta.accent }]}>›</Text>
        </View>
      </View>
    </Pressable>
  );
}

export default function CupHubScreen() {
  const [selected, setSelected] = useState<CompetitionKey | null>(null);

  return (
    <>
      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        <View style={styles.heading}>
          <Text style={styles.headingEyebrow}>AJPA · COMPETICIONES</Text>
          <Text style={styles.headingTitle}>Copas AJPA</Text>
          <Text style={styles.headingSubtitle}>
            Entrá a cada competencia para seguir el bracket, los cruces y los resultados oficiales.
          </Text>
        </View>

        <CupCard competition="champions" onPress={() => setSelected('champions')} />
        <CupCard competition="europa" onPress={() => setSelected('europa')} />
      </ScrollView>

      {selected ? (
        <CupCenterFab
          key={selected}
          hideTrigger
          initialVisible
          initialCompetition={selected}
          onDismiss={() => setSelected(null)}
        />
      ) : null}
    </>
  );
}

const styles = StyleSheet.create({
  content: { padding: 14, paddingBottom: 48, gap: 14 },
  heading: { marginBottom: 2 },
  headingEyebrow: { color: '#b49a65', fontSize: 9, fontWeight: '900', letterSpacing: 1.5 },
  headingTitle: { color: '#fff', fontSize: 27, fontWeight: '900', marginTop: 3 },
  headingSubtitle: { color: '#94a4b2', fontSize: 12, lineHeight: 18, marginTop: 5 },
  card: {
    borderRadius: 21,
    overflow: 'hidden',
    borderWidth: 1.5,
    backgroundColor: '#09131b',
  },
  pressed: { opacity: 0.76 },
  bannerStage: { width: '100%', aspectRatio: 3, backgroundColor: '#03070c', overflow: 'hidden' },
  banner: { width: '100%', height: '100%' },
  copy: { paddingHorizontal: 16, paddingTop: 13, paddingBottom: 14 },
  eyebrow: { fontSize: 8, fontWeight: '900', letterSpacing: 1.25 },
  title: { color: '#fff', fontSize: 21, fontWeight: '900', marginTop: 3 },
  subtitle: { color: '#c5d0d8', fontSize: 11, lineHeight: 16, marginTop: 4 },
  openRow: {
    marginTop: 12,
    minHeight: 42,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.09)',
    backgroundColor: '#040a0f',
    paddingHorizontal: 12,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  openLabel: { color: '#e8eef3', fontSize: 9, fontWeight: '900', letterSpacing: 0.55 },
  chevron: { fontSize: 22, fontWeight: '900' },
});
