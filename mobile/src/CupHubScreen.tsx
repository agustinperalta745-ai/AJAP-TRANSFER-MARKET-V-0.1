// AJPA_CUP_HUB_REFERENCE_20260927
import React, { useState } from 'react';
import { ImageBackground, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import CupCenterFab from './CupCenterFab';
import SeasonHistoryFab from './SeasonHistoryFab';
import TrophyCabinetScreen from './TrophyCabinetFab';

type CompetitionKey = 'champions' | 'europa';

const HERO_BG = require('../assets/cup-menu/hero.jpg');
const CHAMPIONS_BG = require('../assets/cup-menu/champions.jpg');
const EUROPA_BG = require('../assets/cup-menu/europa.jpg');
const RANKING_BG = require('../assets/cup-menu/ranking.jpg');
const CABINET_BG = require('../assets/cup-menu/cabinet.jpg');
const HISTORY_BG = require('../assets/cup-menu/history.jpg');

function CupGlyph({ dark = false }: { dark?: boolean }) {
  return (
    <View style={styles.cupGlyph}>
      <View style={[styles.cupHandle, styles.cupHandleLeft, dark && styles.glyphDarkBorder]} />
      <View style={[styles.cupHandle, styles.cupHandleRight, dark && styles.glyphDarkBorder]} />
      <View style={[styles.cupBowl, dark && styles.glyphDarkBorder]} />
      <View style={[styles.cupStem, dark && styles.glyphDarkFill]} />
      <View style={[styles.cupBase, dark && styles.glyphDarkFill]} />
    </View>
  );
}

function RankingGlyph() {
  return (
    <View style={styles.rankGlyph}>
      <View style={[styles.rankBar, { height: 12 }]} />
      <View style={[styles.rankBar, { height: 21 }]} />
      <View style={[styles.rankBar, { height: 30 }]} />
    </View>
  );
}

function CompetitionCard({
  title,
  subtitle,
  image,
  tone,
  onPress,
}: {
  title: string;
  subtitle: string;
  image: any;
  tone: 'blue' | 'gold';
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={title}
      onPress={onPress}
      style={({ pressed }) => [styles.competitionCard, pressed && styles.pressed]}
    >
      <ImageBackground source={image} resizeMode="cover" imageStyle={styles.competitionImage} style={styles.competitionBackground}>
        <View style={styles.competitionShade} />
        <View style={styles.competitionTopRow}>
          <View style={[styles.iconTile, tone === 'gold' && styles.iconTileGold]}>
            {tone === 'gold' ? <Text style={styles.globeIcon}>◉</Text> : <CupGlyph />}
          </View>
          <View style={styles.competitionCopy}>
            <Text numberOfLines={2} style={styles.competitionTitle}>{title}</Text>
            <Text numberOfLines={3} style={styles.competitionSubtitle}>{subtitle}</Text>
          </View>
          <Text style={styles.chevron}>›</Text>
        </View>
      </ImageBackground>
    </Pressable>
  );
}

function ArchiveCard({
  title,
  subtitle,
  image,
  icon,
  tone,
  onPress,
}: {
  title: string;
  subtitle: string;
  image: any;
  icon: 'ranking' | 'cup' | 'history';
  tone: 'blue' | 'gold' | 'slate';
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={title}
      onPress={onPress}
      style={({ pressed }) => [styles.archiveCard, pressed && styles.pressed]}
    >
      <ImageBackground source={image} resizeMode="cover" imageStyle={styles.archiveImage} style={styles.archiveBackground}>
        <View style={styles.archiveShade} />
        <View style={[
          styles.archiveIconTile,
          tone === 'gold' && styles.archiveIconGold,
          tone === 'slate' && styles.archiveIconSlate,
        ]}>
          {icon === 'ranking' ? <RankingGlyph /> : icon === 'cup' ? <CupGlyph /> : <Text style={styles.historyIcon}>↶</Text>}
        </View>
        <View style={styles.archiveCopy}>
          <Text style={styles.archiveTitle}>{title}</Text>
          <Text numberOfLines={2} style={styles.archiveSubtitle}>{subtitle}</Text>
        </View>
        <Text style={styles.archiveChevron}>›</Text>
      </ImageBackground>
    </Pressable>
  );
}

export default function CupHubScreen() {
  const [selectedCompetition, setSelectedCompetition] = useState<CompetitionKey | null>(null);
  const [cabinetVisible, setCabinetVisible] = useState(false);
  const [historyVisible, setHistoryVisible] = useState(false);

  return (
    <>
      <ScrollView style={styles.screen} contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        <View style={styles.heading}>
          <Text style={styles.headingEyebrow}>AJPA</Text>
          <Text style={styles.headingTitle}>Copas</Text>
        </View>

        <ImageBackground source={HERO_BG} resizeMode="cover" imageStyle={styles.heroImage} style={styles.hero}>
          <View style={styles.heroShade} />
          <View style={styles.heroContent}>
            <View style={styles.heroIconTile}><CupGlyph /></View>
            <View style={styles.heroCopy}>
              <Text style={styles.heroEyebrow}>ESTADO DE COPAS</Text>
              <Text style={styles.heroTitle}>Copas en disputa</Text>
              <Text style={styles.heroCount}>2 competiciones activas</Text>
              <Text style={styles.heroSubtitle}>Champions AJPA y Europa AJPA</Text>
            </View>
          </View>
        </ImageBackground>

        <View style={styles.competitionGrid}>
          <CompetitionCard
            title="Champions AJPA"
            subtitle="Competencia más prestigiosa de AJPA"
            image={CHAMPIONS_BG}
            tone="blue"
            onPress={() => setSelectedCompetition('champions')}
          />
          <CompetitionCard
            title="Europa AJPA"
            subtitle="Segunda competencia más prestigiosa de AJPA"
            image={EUROPA_BG}
            tone="gold"
            onPress={() => setSelectedCompetition('europa')}
          />
        </View>

        <Text style={styles.sectionLabel}>ARCHIVO Y RANKINGS</Text>

        <ArchiveCard
          title="Ranking de títulos"
          subtitle="Los clubes más ganadores de AJPA"
          image={RANKING_BG}
          icon="ranking"
          tone="gold"
          onPress={() => setCabinetVisible(true)}
        />
        <ArchiveCard
          title="Vitrina de campeones"
          subtitle="Campeones históricos de cada competición"
          image={CABINET_BG}
          icon="cup"
          tone="blue"
          onPress={() => setCabinetVisible(true)}
        />
        <ArchiveCard
          title="Historial"
          subtitle="Finales, temporadas y registros anteriores"
          image={HISTORY_BG}
          icon="history"
          tone="slate"
          onPress={() => setHistoryVisible(true)}
        />
      </ScrollView>

      {selectedCompetition ? (
        <CupCenterFab
          key={selectedCompetition}
          hideTrigger
          initialVisible
          initialCompetition={selectedCompetition}
          onDismiss={() => setSelectedCompetition(null)}
        />
      ) : null}
      {cabinetVisible ? <TrophyCabinetScreen onClose={() => setCabinetVisible(false)} /> : null}
      {historyVisible ? <SeasonHistoryFab hideTrigger initialVisible onDismiss={() => setHistoryVisible(false)} /> : null}
    </>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: '#020912' },
  content: { paddingHorizontal: 12, paddingTop: 8, paddingBottom: 42, gap: 10 },
  pressed: { opacity: 0.78, transform: [{ scale: 0.99 }] },

  heading: { paddingHorizontal: 4, paddingTop: 2, paddingBottom: 2 },
  headingEyebrow: { color: '#21a7ff', fontSize: 10, fontWeight: '900', letterSpacing: 2.6 },
  headingTitle: { color: '#fff', fontSize: 28, lineHeight: 32, fontWeight: '900', marginTop: 1 },

  hero: {
    height: 154,
    borderRadius: 22,
    borderWidth: 1.4,
    borderColor: '#158fdf',
    overflow: 'hidden',
    justifyContent: 'center',
    backgroundColor: '#04111d',
  },
  heroImage: { borderRadius: 21 },
  heroShade: { ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(1,10,19,0.39)' },
  heroContent: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 14, gap: 13 },
  heroIconTile: {
    width: 61, height: 61, borderRadius: 17, alignItems: 'center', justifyContent: 'center',
    backgroundColor: '#1599f1', borderWidth: 1, borderColor: '#45b8ff',
  },
  heroCopy: { flex: 1, minWidth: 0 },
  heroEyebrow: { color: '#23a8ff', fontSize: 8.5, fontWeight: '900', letterSpacing: 1.8 },
  heroTitle: { color: '#fff', fontSize: 22, fontWeight: '900', marginTop: 4 },
  heroCount: { color: '#129cff', fontSize: 13.5, fontWeight: '900', marginTop: 4 },
  heroSubtitle: { color: '#b9c8d4', fontSize: 11.5, marginTop: 4 },

  competitionGrid: { flexDirection: 'row', gap: 8 },
  competitionCard: {
    flex: 1,
    minWidth: 0,
    height: 248,
    borderRadius: 20,
    borderWidth: 1.35,
    borderColor: '#177fb8',
    overflow: 'hidden',
    backgroundColor: '#06111a',
  },
  competitionBackground: { flex: 1 },
  competitionImage: { borderRadius: 19 },
  competitionShade: { ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(0,9,17,0.15)' },
  competitionTopRow: { flexDirection: 'row', alignItems: 'flex-start', padding: 10, gap: 8 },
  iconTile: {
    width: 47, height: 47, borderRadius: 14, alignItems: 'center', justifyContent: 'center',
    backgroundColor: '#238ed0', borderWidth: 1, borderColor: '#4ab8f4',
  },
  iconTileGold: { backgroundColor: '#c79016', borderColor: '#e5b743' },
  globeIcon: { color: '#fff', fontSize: 28, lineHeight: 30, fontWeight: '900' },
  competitionCopy: { flex: 1, minWidth: 0, paddingTop: 1 },
  competitionTitle: { color: '#fff', fontSize: 16.5, lineHeight: 19, fontWeight: '900' },
  competitionSubtitle: { color: '#b6c4d0', fontSize: 10.5, lineHeight: 14, marginTop: 4 },
  chevron: { color: '#08a6ff', fontSize: 31, lineHeight: 34, fontWeight: '800', marginTop: 5 },

  sectionLabel: { color: '#169ee8', fontSize: 10, fontWeight: '900', letterSpacing: 1.8, marginTop: 3, marginBottom: 1 },
  archiveCard: {
    height: 82,
    borderRadius: 18,
    borderWidth: 1.2,
    borderColor: '#176b9f',
    overflow: 'hidden',
    backgroundColor: '#07121b',
  },
  archiveBackground: { flex: 1, flexDirection: 'row', alignItems: 'center', paddingHorizontal: 11, gap: 11 },
  archiveImage: { borderRadius: 17 },
  archiveShade: { ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(1,10,18,0.42)' },
  archiveIconTile: {
    width: 47, height: 47, borderRadius: 14, alignItems: 'center', justifyContent: 'center',
    backgroundColor: '#1888c5', borderWidth: 1, borderColor: 'rgba(111,203,255,0.65)',
  },
  archiveIconGold: { backgroundColor: '#c38a12', borderColor: '#e9bd4e' },
  archiveIconSlate: { backgroundColor: '#66849a', borderColor: '#8ca8ba' },
  archiveCopy: { flex: 1, minWidth: 0, zIndex: 1 },
  archiveTitle: { color: '#fff', fontSize: 16, fontWeight: '900' },
  archiveSubtitle: { color: '#b6c4d0', fontSize: 10.5, lineHeight: 14, marginTop: 2 },
  archiveChevron: { color: '#08a6ff', fontSize: 30, lineHeight: 32, fontWeight: '800', zIndex: 1 },

  cupGlyph: { width: 34, height: 36, alignItems: 'center', justifyContent: 'flex-start' },
  cupBowl: { width: 21, height: 16, borderWidth: 2.5, borderColor: '#fff', borderTopWidth: 2.5, borderRadius: 5, marginTop: 2 },
  cupHandle: { position: 'absolute', top: 5, width: 10, height: 12, borderWidth: 2.2, borderColor: '#fff', borderRadius: 7 },
  cupHandleLeft: { left: 0 },
  cupHandleRight: { right: 0 },
  cupStem: { width: 3, height: 8, backgroundColor: '#fff', marginTop: 1.5 },
  cupBase: { width: 18, height: 3, borderRadius: 2, backgroundColor: '#fff', marginTop: 1 },
  glyphDarkBorder: { borderColor: '#fff' },
  glyphDarkFill: { backgroundColor: '#fff' },

  rankGlyph: { width: 31, height: 31, flexDirection: 'row', alignItems: 'flex-end', justifyContent: 'space-between' },
  rankBar: { width: 5, borderRadius: 3, backgroundColor: '#fff' },
  historyIcon: { color: '#fff', fontSize: 31, lineHeight: 33, fontWeight: '700' },
});
