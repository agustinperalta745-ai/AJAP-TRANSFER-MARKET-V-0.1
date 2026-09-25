import React, { useState } from 'react';
import {
  Pressable,
  ScrollView,
  StatusBar,
  StyleSheet,
  Text,
  View,
} from 'react-native';

type Section = 'Inicio' | 'Mercado' | 'Mi Club' | 'Liga' | 'Copas' | 'Más';

const ITEMS: Array<{ title: Section; subtitle: string }> = [
  { title: 'Mercado', subtitle: 'Fichajes, ofertas y negociaciones' },
  { title: 'Mi Club', subtitle: 'Plantel, tácticas y gestión' },
  { title: 'Liga', subtitle: 'Tabla, partidos y estadísticas' },
  { title: 'Copas', subtitle: 'Competencias AJPA' },
  { title: 'Más', subtitle: 'Perfil y herramientas' },
];

export default function App() {
  const [selected, setSelected] = useState<Section>('Inicio');

  return (
    <View style={s.root}>
      <StatusBar barStyle="light-content" backgroundColor="#06111B" translucent={false} />

      <ScrollView contentContainerStyle={s.content} showsVerticalScrollIndicator={false}>
        <View style={s.header}>
          <View style={s.logoBox}><Text style={s.logoText}>AJ</Text></View>
          <View style={s.headerCopy}>
            <Text style={s.brand}>AJPA</Text>
            <Text style={s.brandSub}>ASOCIACIÓN DE JUGADORES DE PES ARGENTINA</Text>
          </View>
        </View>

        <View style={s.labBadge}>
          <View style={s.dot} />
          <Text style={s.labText}>UI LAB · ARRANQUE SEGURO</Text>
        </View>

        <View style={s.hero}>
          <Text style={s.heroEyebrow}>TEMPORADA 2</Text>
          <Text style={s.heroTitle}>La pasión sigue en AJPA</Text>
          <Text style={s.heroText}>
            Esta build elimina temporalmente API, escudos, imágenes pesadas e iconos externos para aislar el crash.
          </Text>
          <View style={s.metaRow}>
            <View style={s.metaBox}><Text style={s.metaSmall}>ESTADO</Text><Text style={s.metaValue}>APP ABIERTA</Text></View>
            <View style={s.metaBox}><Text style={s.metaSmall}>VISTA</Text><Text style={s.metaValue}>{selected.toUpperCase()}</Text></View>
          </View>
        </View>

        <Text style={s.sectionTitle}>Menú principal</Text>
        <View style={s.grid}>
          {ITEMS.map((item, index) => (
            <Pressable
              key={item.title}
              onPress={() => setSelected(item.title)}
              style={({ pressed }) => [s.card, pressed && s.pressed, selected === item.title && s.cardActive]}
            >
              <View style={s.cardIcon}><Text style={s.cardIconText}>{String(index + 1).padStart(2, '0')}</Text></View>
              <Text style={s.cardTitle}>{item.title}</Text>
              <Text style={s.cardSub}>{item.subtitle}</Text>
              <Text style={s.chevron}>›</Text>
            </Pressable>
          ))}
        </View>

        <View style={s.info}>
          <Text style={s.infoTitle}>PRUEBA DE ESTABILIDAD</Text>
          <Text style={s.infoText}>
            Si esta pantalla abre y se mantiene estable, el crash estaba en una dependencia visual o carga inicial y las vamos reactivando de a una.
          </Text>
        </View>
      </ScrollView>

      <View style={s.bottom}>
        {(['Inicio', 'Mercado', 'Mi Club', 'Liga', 'Copas', 'Más'] as Section[]).map((item) => (
          <Pressable key={item} onPress={() => setSelected(item)} style={s.bottomItem}>
            <View style={[s.bottomDot, selected === item && s.bottomDotActive]} />
            <Text style={[s.bottomText, selected === item && s.bottomTextActive]}>{item}</Text>
          </Pressable>
        ))}
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#06111B' },
  content: { paddingHorizontal: 16, paddingTop: 18, paddingBottom: 110 },
  header: { flexDirection: 'row', alignItems: 'center', marginBottom: 14 },
  logoBox: { width: 56, height: 56, borderRadius: 18, borderWidth: 1, borderColor: '#2D92FF', backgroundColor: '#0B2234', alignItems: 'center', justifyContent: 'center' },
  logoText: { color: '#F5FAFE', fontSize: 20, fontWeight: '900', letterSpacing: 1 },
  headerCopy: { flex: 1, marginLeft: 12 },
  brand: { color: '#F5FAFE', fontSize: 31, lineHeight: 33, fontWeight: '900', letterSpacing: 1 },
  brandSub: { color: '#79C8FF', fontSize: 7.5, fontWeight: '800', letterSpacing: 1.5, marginTop: 3 },
  labBadge: { alignSelf: 'flex-start', flexDirection: 'row', alignItems: 'center', borderRadius: 999, borderWidth: 1, borderColor: '#1C4F73', backgroundColor: '#0A2031', paddingHorizontal: 10, paddingVertical: 6, marginBottom: 12 },
  dot: { width: 7, height: 7, borderRadius: 4, backgroundColor: '#42D97F', marginRight: 7 },
  labText: { color: '#9ED5FF', fontSize: 9, fontWeight: '900', letterSpacing: 1.2 },
  hero: { borderRadius: 22, borderWidth: 1, borderColor: '#245B80', backgroundColor: '#0B1E2D', padding: 20, minHeight: 224, justifyContent: 'flex-end' },
  heroEyebrow: { color: '#79C8FF', fontSize: 10, fontWeight: '900', letterSpacing: 2.2 },
  heroTitle: { color: '#F5FAFE', fontSize: 29, lineHeight: 33, fontWeight: '900', marginTop: 8 },
  heroText: { color: '#A7B8C6', fontSize: 11, lineHeight: 16, marginTop: 9 },
  metaRow: { flexDirection: 'row', marginTop: 18 },
  metaBox: { flex: 1, borderTopWidth: 1, borderTopColor: '#23465F', paddingTop: 10 },
  metaSmall: { color: '#7890A1', fontSize: 8, fontWeight: '800', letterSpacing: 1.1 },
  metaValue: { color: '#F5FAFE', fontSize: 11, fontWeight: '900', marginTop: 4 },
  sectionTitle: { color: '#F5FAFE', fontSize: 17, fontWeight: '900', marginTop: 18, marginBottom: 10 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between' },
  card: { width: '48.4%', minHeight: 142, borderRadius: 19, borderWidth: 1, borderColor: '#203E54', backgroundColor: '#0D2232', padding: 14, marginBottom: 10 },
  cardActive: { borderColor: '#2D92FF', backgroundColor: '#0D293E' },
  pressed: { opacity: 0.75 },
  cardIcon: { width: 44, height: 44, borderRadius: 13, backgroundColor: '#123A57', alignItems: 'center', justifyContent: 'center', marginBottom: 12 },
  cardIconText: { color: '#79C8FF', fontSize: 12, fontWeight: '900' },
  cardTitle: { color: '#F5FAFE', fontSize: 17, fontWeight: '900' },
  cardSub: { color: '#93A7B8', fontSize: 10.5, lineHeight: 15, marginTop: 4, paddingRight: 16 },
  chevron: { position: 'absolute', right: 12, top: 68, color: '#36A7FF', fontSize: 24, fontWeight: '900' },
  info: { marginTop: 4, borderRadius: 18, borderWidth: 1, borderColor: '#1D4D6C', backgroundColor: '#0A1D2C', padding: 14 },
  infoTitle: { color: '#79C8FF', fontSize: 9, fontWeight: '900', letterSpacing: 1.4 },
  infoText: { color: '#A6B8C5', fontSize: 10.5, lineHeight: 15, marginTop: 5 },
  bottom: { position: 'absolute', left: 0, right: 0, bottom: 0, height: 82, flexDirection: 'row', backgroundColor: '#07141F', borderTopWidth: 1, borderTopColor: '#19384D', paddingBottom: 8 },
  bottomItem: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  bottomDot: { width: 7, height: 7, borderRadius: 4, backgroundColor: '#40586A', marginBottom: 6 },
  bottomDotActive: { width: 19, backgroundColor: '#36A7FF' },
  bottomText: { color: '#7F93A2', fontSize: 8, fontWeight: '700' },
  bottomTextActive: { color: '#79C8FF', fontWeight: '900' },
});
