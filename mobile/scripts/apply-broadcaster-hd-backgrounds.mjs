import fs from 'node:fs';

const uiPath = new URL('../src/BotParityAppV2.tsx', import.meta.url);
let ui = fs.readFileSync(uiPath, 'utf8');

if (!ui.includes('bcHdPageArt')) {
  const scrollAnchor = `      showsVerticalScrollIndicator={false}\n    >`;
  if (!ui.includes(scrollAnchor)) throw new Error('Broadcaster HD: no encontré el ScrollView de Inicio');
  ui = ui.replace(scrollAnchor, `${scrollAnchor}\n      <View pointerEvents="none" style={s.bcHdPageArt}>\n        <View style={s.bcHdPageBeamA} />\n        <View style={s.bcHdPageBeamB} />\n        <View style={s.bcHdPageGlowA} />\n        <View style={s.bcHdPageGlowB} />\n        <View style={s.bcHdPageArc} />\n      </View>`);

  const heroAnchor = `          resizeMode="cover"\n        >\n          <View style={s.bcHeroShade}>`;
  if (!ui.includes(heroAnchor)) throw new Error('Broadcaster HD: no encontré el fondo del Centro de mando');
  ui = ui.replace(heroAnchor, `          resizeMode="cover"\n        >\n          <View pointerEvents="none" style={s.bcHdHeroArt}>\n            <View style={s.bcHdHeroBase} />\n            <View style={s.bcHdHeroBeamA} />\n            <View style={s.bcHdHeroBeamB} />\n            <View style={s.bcHdHeroBall}>\n              <View style={s.bcHdHeroBallRingA} />\n              <View style={s.bcHdHeroBallRingB} />\n              <View style={s.bcHdHeroBallCore} />\n              <View style={s.bcHdHeroBallSeamA} />\n              <View style={s.bcHdHeroBallSeamB} />\n              <View style={s.bcHdHeroBallSeamC} />\n            </View>\n          </View>\n          <View style={s.bcHeroShade}>`);

  const styleClose = '\n});';
  const stylePos = ui.lastIndexOf(styleClose);
  if (stylePos < 0) throw new Error('Broadcaster HD: no encontré el StyleSheet principal');
  const hdStyles = String.raw`
  bcHdPageArt: { position: 'absolute', left: -20, right: -20, top: -30, bottom: -80, overflow: 'hidden', opacity: 0.86 },
  bcHdPageBeamA: { position: 'absolute', width: 150, height: 980, right: 56, top: 90, backgroundColor: 'rgba(12,54,86,0.18)', transform: [{ rotate: '20deg' }] },
  bcHdPageBeamB: { position: 'absolute', width: 72, height: 900, right: 145, top: 380, backgroundColor: 'rgba(16,83,126,0.10)', transform: [{ rotate: '20deg' }] },
  bcHdPageGlowA: { position: 'absolute', width: 230, height: 230, borderRadius: 230, right: -70, top: 340, backgroundColor: 'rgba(30,125,190,0.055)', borderWidth: 20, borderColor: 'rgba(30,125,190,0.03)' },
  bcHdPageGlowB: { position: 'absolute', width: 190, height: 190, borderRadius: 190, left: -80, top: 1040, backgroundColor: 'rgba(45,128,183,0.045)' },
  bcHdPageArc: { position: 'absolute', width: 470, height: 180, borderRadius: 240, left: -60, top: 790, borderTopWidth: 1, borderColor: 'rgba(78,152,205,0.075)', transform: [{ rotate: '-5deg' }] },
  bcHdHeroArt: { position: 'absolute', left: 0, right: 0, top: 0, bottom: 0, overflow: 'hidden' },
  bcHdHeroBase: { position: 'absolute', left: 0, right: 0, top: 0, bottom: 0, backgroundColor: 'rgba(1,9,17,0.82)' },
  bcHdHeroBeamA: { position: 'absolute', width: 118, height: 350, right: 112, top: -62, backgroundColor: 'rgba(23,95,143,0.24)', transform: [{ rotate: '24deg' }] },
  bcHdHeroBeamB: { position: 'absolute', width: 44, height: 330, right: 175, top: -55, backgroundColor: 'rgba(34,124,184,0.11)', transform: [{ rotate: '24deg' }] },
  bcHdHeroBall: { position: 'absolute', width: 205, height: 205, borderRadius: 205, right: -28, top: 20, borderWidth: 2, borderColor: 'rgba(86,161,219,0.38)', backgroundColor: 'rgba(3,11,19,0.82)' },
  bcHdHeroBallRingA: { position: 'absolute', width: 155, height: 155, borderRadius: 155, left: 24, top: 24, borderWidth: 1, borderColor: 'rgba(88,161,214,0.18)' },
  bcHdHeroBallRingB: { position: 'absolute', width: 112, height: 112, borderRadius: 112, left: 45, top: 45, borderWidth: 1, borderColor: 'rgba(88,161,214,0.12)' },
  bcHdHeroBallCore: { position: 'absolute', width: 48, height: 48, left: 78, top: 78, backgroundColor: '#02070d', borderWidth: 1, borderColor: 'rgba(83,150,203,0.22)', transform: [{ rotate: '45deg' }] },
  bcHdHeroBallSeamA: { position: 'absolute', width: 2, height: 73, left: 101, top: 8, backgroundColor: 'rgba(76,146,200,0.22)' },
  bcHdHeroBallSeamB: { position: 'absolute', width: 2, height: 68, left: 58, top: 58, backgroundColor: 'rgba(76,146,200,0.18)', transform: [{ rotate: '58deg' }] },
  bcHdHeroBallSeamC: { position: 'absolute', width: 2, height: 68, right: 58, top: 58, backgroundColor: 'rgba(76,146,200,0.18)', transform: [{ rotate: '-58deg' }] },
`;
  ui = ui.slice(0, stylePos) + hdStyles + ui.slice(stylePos);
  fs.writeFileSync(uiPath, ui);
}

const seasonPath = new URL('../src/SeasonCountdownBanner.tsx', import.meta.url);
let season = fs.readFileSync(seasonPath, 'utf8');
if (!season.includes('bcSeasonArt')) {
  const bannerAnchor = `<View style={[styles.banner, closed && styles.bannerClosed]}>`;
  if (!season.includes(bannerAnchor)) throw new Error('Broadcaster HD: no encontré el banner de temporada');
  season = season.replace(bannerAnchor, `${bannerAnchor}\n        <View pointerEvents="none" style={styles.bcSeasonArt}>\n          <View style={styles.bcSeasonShade} />\n          <View style={styles.bcSeasonBeamA} />\n          <View style={styles.bcSeasonBeamB} />\n          <View style={styles.bcSeasonStadiumArc} />\n          <View style={styles.bcSeasonStadiumArcInner} />\n          <View style={styles.bcSeasonPitch} />\n          <View style={[styles.bcSeasonSpark, { left: '12%', top: 18 }]} />\n          <View style={[styles.bcSeasonSpark, { left: '28%', top: 34 }]} />\n          <View style={[styles.bcSeasonSpark, { left: '64%', top: 22 }]} />\n          <View style={[styles.bcSeasonSpark, { left: '79%', top: 42 }]} />\n        </View>`);

  const seasonClose = '\n});';
  const seasonStylePos = season.lastIndexOf(seasonClose);
  if (seasonStylePos < 0) throw new Error('Broadcaster HD: no encontré estilos del banner');
  const seasonStyles = String.raw`
  bcSeasonArt: { position: 'absolute', left: 0, right: 0, top: 0, bottom: 0, overflow: 'hidden', borderRadius: 22 },
  bcSeasonShade: { position: 'absolute', left: 0, right: 0, top: 0, bottom: 0, backgroundColor: 'rgba(1,9,17,0.64)' },
  bcSeasonBeamA: { position: 'absolute', width: 110, height: 250, left: '44%', top: -72, backgroundColor: 'rgba(22,92,139,0.15)', transform: [{ rotate: '18deg' }] },
  bcSeasonBeamB: { position: 'absolute', width: 50, height: 230, left: '53%', top: -72, backgroundColor: 'rgba(35,121,180,0.08)', transform: [{ rotate: '18deg' }] },
  bcSeasonStadiumArc: { position: 'absolute', width: 380, height: 125, borderRadius: 220, left: '50%', marginLeft: -190, bottom: -54, borderTopWidth: 2, borderColor: 'rgba(74,151,207,0.20)' },
  bcSeasonStadiumArcInner: { position: 'absolute', width: 315, height: 100, borderRadius: 180, left: '50%', marginLeft: -158, bottom: -45, borderTopWidth: 1, borderColor: 'rgba(74,151,207,0.12)' },
  bcSeasonPitch: { position: 'absolute', width: 116, height: 78, left: '50%', marginLeft: -58, bottom: -13, borderWidth: 1, borderColor: 'rgba(83,159,214,0.12)', backgroundColor: 'rgba(3,23,36,0.28)', transform: [{ perspective: 500 }, { rotateX: '58deg' }] },
  bcSeasonSpark: { position: 'absolute', width: 2, height: 2, borderRadius: 2, backgroundColor: 'rgba(159,211,247,0.48)' },
`;
  season = season.slice(0, seasonStylePos) + seasonStyles + season.slice(seasonStylePos);
  fs.writeFileSync(seasonPath, season);
}

console.log('AJPA Broadcaster: fondos HD vectoriales aplicados en Inicio, Centro de mando y cierre de temporada.');
