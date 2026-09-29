import React, { useEffect, useMemo, useState } from 'react';
import {
  ImageBackground,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import {
  Award,
  ChartNoAxesColumnIncreasing,
  Globe2,
  History,
  Trophy,
} from 'lucide-react-native';

import { apiRequest } from './api';
import TrophyCabinetScreen from './TrophyCabinetFab';
import {
  CUP_CABINET_BG,
  CUP_CHAMPIONS_BG,
  CUP_EUROPA_BG,
  CUP_HERO_BG,
  CUP_HISTORY_BG,
  CUP_RANKING_BG,
} from './cup_menu_assets';

type TrophyKey = 'league' | 'champions' | 'europa';

type CupsPayload = {
  rules?: { season_number?: number | null } | null;
  edition?: {
    season_number?: number | null;
    status?: string | null;
  } | null;
};

const HERO = { uri: CUP_HERO_BG } as const;
const CHAMPIONS = { uri: CUP_CHAMPIONS_BG } as const;
const EUROPA = { uri: CUP_EUROPA_BG } as const;
const RANKING = { uri: CUP_RANKING_BG } as const;
const VITRINA = { uri: CUP_CABINET_BG } as const;
const HISTORIAL = { uri: CUP_HISTORY_BG } as const;

const BLUE = '#28A5F5';
const WHITE = '#F5FAFE';
const MUTED = '#9AAEBD';
const BORDER = '#24506D';
const PANEL = '#0A2233';

function IconTile({
  children,
  tone = '#2589D8',
}: {
  children: React.ReactNode;
  tone?: string;
}) {
  return <View style={[styles.iconTile, { backgroundColor: tone }]}>{children}</View>;
}

function CompetitionCard({
  title,
  subtitle,
  background,
  icon,
  tone,
  onPress,
}: {
  title: string;
  subtitle: string;
  background: any;
  icon: React.ReactNode;
  tone: string;
  onPress: () => void;
}) {
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [styles.competitionCard, pressed && styles.pressed]}
    >
      <ImageBackground
        source={background}
        resizeMode="cover"
        style={StyleSheet.absoluteFillObject}
        imageStyle={styles.competitionImage}
      />
      <View style={styles.competitionShade} />
      <View style={styles.competitionTop}>
        <IconTile tone={tone}>{icon}</IconTile>
        <View style={styles.competitionCopy}>
          <Text style={styles.competitionTitle}>{title}</Text>
          <Text style={styles.competitionSubtitle}>{subtitle}</Text>
        </View>
        <Text style={styles.chevron}>›</Text>
      </View>
    </Pressable>
  );
}

function ArchiveCard({
  title,
  subtitle,
  background,
  icon,
  tone,
  onPress,
}: {
  title: string;
  subtitle: string;
  background: any;
  icon: React.ReactNode;
  tone: string;
  onPress: () => void;
}) {
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [styles.archiveCard, pressed && styles.pressed]}
    >
      <ImageBackground
        source={background}
        resizeMode="cover"
        style={StyleSheet.absoluteFillObject}
        imageStyle={styles.archiveImage}
      />
      <View style={styles.archiveShade} />
      <IconTile tone={tone}>{icon}</IconTile>
      <View style={styles.archiveCopy}>
        <Text style={styles.archiveTitle}>{title}</Text>
        <Text style={styles.archiveSubtitle} numberOfLines={2}>{subtitle}</Text>
      </View>
      <Text style={styles.archiveChevron}>›</Text>
    </Pressable>
  );
}

export default function CopasMenuScreen() {
  const [cups, setCups] = useState<CupsPayload | null>(null);
  const [detail, setDetail] = useState<TrophyKey | null>(null);

  useEffect(() => {
    let mounted = true;
    void apiRequest<CupsPayload>('/api/v1/cups')
      .then((payload) => {
        if (mounted) setCups(payload);
      })
      .catch(() => {
        // El menú sigue siendo utilizable aunque el resumen no responda.
      });
    return () => {
      mounted = false;
    };
  }, []);

  const stateCopy = useMemo(() => {
    const status = String(cups?.edition?.status || '').toUpperCase();
    if (status === 'ACTIVE') return '2 competiciones activas';
    if (status === 'DRAFT') return '2 competiciones en preparación';
    if (status === 'FINISHED') return 'Copas finalizadas';
    return '2 competiciones';
  }, [cups]);

  return (
    <>
      <ScrollView
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.hero}>
          <ImageBackground
            source={HERO}
            resizeMode="cover"
            style={StyleSheet.absoluteFillObject}
            imageStyle={styles.heroImage}
          />
          <View style={styles.heroShade} />
          <IconTile tone="#2497EA"><Trophy size={29} color="#FFFFFF" strokeWidth={2.15} /></IconTile>
          <View style={styles.heroCopy}>
            <Text style={styles.heroEyebrow}>ESTADO DE COPAS</Text>
            <Text style={styles.heroTitle}>Copas en disputa</Text>
            <Text style={styles.heroState}>{stateCopy}</Text>
            <Text style={styles.heroSubtitle}>Champions AJPA y Europa AJPA</Text>
          </View>
        </View>

        <View style={styles.competitionGrid}>
          <CompetitionCard
            title="Champions AJPA"
            subtitle="Competencia más prestigiosa de AJPA"
            background={CHAMPIONS}
            tone="#2C83C5"
            icon={<Trophy size={25} color="#FFFFFF" strokeWidth={2.15} />}
            onPress={() => setDetail('champions')}
          />
          <CompetitionCard
            title="Europa AJPA"
            subtitle="Segunda competencia más prestigiosa de AJPA"
            background={EUROPA}
            tone="#B8891D"
            icon={<Globe2 size={25} color="#FFFFFF" strokeWidth={2.15} />}
            onPress={() => setDetail('europa')}
          />
        </View>

        <Text style={styles.sectionLabel}>ARCHIVO Y RANKINGS</Text>

        <ArchiveCard
          title="Ranking de títulos"
          subtitle="Los clubes más ganadores de AJPA"
          background={RANKING}
          tone="#B8891D"
          icon={<ChartNoAxesColumnIncreasing size={25} color="#FFFFFF" strokeWidth={2.15} />}
          onPress={() => setDetail('league')}
        />
        <ArchiveCard
          title="Vitrina de campeones"
          subtitle="Campeones históricos de cada competición"
          background={VITRINA}
          tone="#2C83C5"
          icon={<Award size={25} color="#FFFFFF" strokeWidth={2.15} />}
          onPress={() => setDetail('league')}
        />
        <ArchiveCard
          title="Historial"
          subtitle="Finales, temporadas y registros anteriores"
          background={HISTORIAL}
          tone="#5C7181"
          icon={<History size={25} color="#FFFFFF" strokeWidth={2.15} />}
          onPress={() => setDetail('league')}
        />
      </ScrollView>

      {detail ? (
        <TrophyCabinetScreen
          key={detail}
          initialTrophy={detail}
          onClose={() => setDetail(null)}
        />
      ) : null}
    </>
  );
}

const styles = StyleSheet.create({
  content: {
    paddingHorizontal: 14,
    paddingTop: 14,
    paddingBottom: 112,
    gap: 10,
    backgroundColor: '#07131F',
  },
  pressed: { opacity: 0.76, transform: [{ scale: 0.994 }] },

  hero: {
    minHeight: 136,
    borderRadius: 22,
    borderWidth: 1.25,
    borderColor: '#2C789F',
    backgroundColor: PANEL,
    overflow: 'hidden',
    paddingHorizontal: 14,
    paddingVertical: 13,
    flexDirection: 'row',
    alignItems: 'center',
  },
  heroImage: { opacity: 0.82 },
  heroShade: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(4, 17, 28, 0.48)',
  },
  heroCopy: { flex: 1, minWidth: 0, marginLeft: 13 },
  heroEyebrow: {
    color: '#43B8FF',
    fontSize: 8.7,
    fontWeight: '900',
    letterSpacing: 1.45,
  },
  heroTitle: {
    color: WHITE,
    fontSize: 19,
    lineHeight: 22,
    fontWeight: '900',
    marginTop: 5,
  },
  heroState: {
    color: BLUE,
    fontSize: 12.5,
    lineHeight: 16,
    fontWeight: '900',
    marginTop: 4,
  },
  heroSubtitle: {
    color: '#AFBFCA',
    fontSize: 10,
    lineHeight: 14,
    marginTop: 3,
  },

  competitionGrid: {
    flexDirection: 'row',
    gap: 10,
  },
  competitionCard: {
    flex: 1,
    minHeight: 252,
    borderRadius: 19,
    borderWidth: 1,
    borderColor: BORDER,
    backgroundColor: PANEL,
    overflow: 'hidden',
    padding: 11,
  },
  competitionImage: { opacity: 0.91 },
  competitionShade: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(4, 18, 29, 0.34)',
  },
  competitionTop: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 8,
  },
  competitionCopy: {
    flex: 1,
    minWidth: 0,
    paddingTop: 1,
  },
  competitionTitle: {
    color: WHITE,
    fontSize: 15.5,
    lineHeight: 19,
    fontWeight: '900',
    textShadowColor: 'rgba(0,0,0,0.75)',
    textShadowOffset: { width: 0, height: 1 },
    textShadowRadius: 3,
  },
  competitionSubtitle: {
    color: '#C1CDD6',
    fontSize: 10,
    lineHeight: 14,
    marginTop: 5,
    textShadowColor: 'rgba(0,0,0,0.8)',
    textShadowOffset: { width: 0, height: 1 },
    textShadowRadius: 3,
  },

  iconTile: {
    width: 49,
    height: 49,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: '#318DC4',
    alignItems: 'center',
    justifyContent: 'center',
  },
  chevron: {
    color: BLUE,
    fontSize: 27,
    lineHeight: 30,
    fontWeight: '900',
    marginTop: 5,
  },

  sectionLabel: {
    color: '#43B8FF',
    fontSize: 9.4,
    fontWeight: '900',
    letterSpacing: 1.45,
    marginTop: 3,
    marginBottom: 1,
  },
  archiveCard: {
    minHeight: 79,
    borderRadius: 18,
    borderWidth: 1,
    borderColor: BORDER,
    backgroundColor: PANEL,
    overflow: 'hidden',
    paddingHorizontal: 11,
    paddingVertical: 10,
    flexDirection: 'row',
    alignItems: 'center',
  },
  archiveImage: { opacity: 0.82 },
  archiveShade: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(4, 18, 29, 0.47)',
  },
  archiveCopy: { flex: 1, minWidth: 0, marginLeft: 11 },
  archiveTitle: {
    color: WHITE,
    fontSize: 14.3,
    lineHeight: 17,
    fontWeight: '900',
    textShadowColor: 'rgba(0,0,0,0.75)',
    textShadowOffset: { width: 0, height: 1 },
    textShadowRadius: 2,
  },
  archiveSubtitle: {
    color: MUTED,
    fontSize: 9.2,
    lineHeight: 12.5,
    marginTop: 3,
  },
  archiveChevron: {
    color: BLUE,
    fontSize: 24,
    fontWeight: '900',
    marginLeft: 7,
  },
});
