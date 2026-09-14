import fs from 'node:fs';

const file = new URL('../src/BotParityAppV2.tsx', import.meta.url);
let ui = fs.readFileSync(file, 'utf8');

const titleMarker = 'function Title({ eyebrow, title, subtitle }: { eyebrow: string; title: string; subtitle?: string }) {';
if (!ui.includes(titleMarker)) throw new Error('AJPA generated repair: no encontré Title');

const commandHero = String.raw`function CommandHero() {
  return (
    <View style={s.commandHero}>
      <View pointerEvents="none" style={s.vectorFill}><HeroArt /></View>
      <View style={s.commandHeroShade}>
        <View style={s.commandHeroCopy}>
          <Text style={s.commandHeroTitle}>Centro de mando AJPA</Text>
          <Text style={s.commandHeroSubtitle}>Gestioná, competí y viví el fútbol virtual en un solo lugar.</Text>
          <View style={s.commandHeroRule} />
          <Text style={s.commandHeroMeta}>DISCIPLINA   ·   ESTRATEGIA   ·   COMUNIDAD</Text>
        </View>
        <View style={s.commandHeroTag}>
          <Text style={s.commandHeroTagText}>EL FÚTBOL</Text>
          <Text style={s.commandHeroTagText}>NOS UNE</Text>
          <View style={s.commandHeroTagRule} />
        </View>
      </View>
    </View>
  );
}`;

const radio = String.raw`function RadioPasilloStrip({ marketOpen, onPress }: { marketOpen: boolean; onPress: () => void }) {
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [s.radioStrip, pressed && { opacity: 0.78 }]}>
      <View style={s.radioIconWrap}><Text style={s.radioIcon}>◉</Text></View>
      <View style={s.flex}>
        <Text style={s.radioEyebrow}>RADIO PASILLO</Text>
        <Text style={s.radioHeadline}>{marketOpen ? 'Mercado abierto · últimas novedades AJPA' : 'Mercado cerrado · noticias de la liga'}</Text>
      </View>
      <Text style={s.radioChevron}>›</Text>
    </Pressable>
  );
}`;

const blocks = [];
if (!ui.includes('function CommandHero()')) blocks.push(commandHero);
if (!ui.includes('function RadioPasilloStrip(')) blocks.push(radio);
if (blocks.length) ui = ui.replace(titleMarker, `${blocks.join('\n\n')}\n\n${titleMarker}`);

if (!ui.includes('function CommandHero()')) throw new Error('AJPA generated repair: CommandHero no quedó definido');
if (!ui.includes('function RadioPasilloStrip(')) throw new Error('AJPA generated repair: RadioPasilloStrip no quedó definido');

fs.writeFileSync(file, ui);
console.log('AJPA generated repair: hero y Radio Pasillo restaurados después del reemplazo de WideTile.');
