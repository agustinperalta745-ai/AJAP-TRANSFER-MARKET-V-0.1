import fs from 'node:fs';

const path = new URL('../src/CupCenterFab.tsx', import.meta.url);
let source = fs.readFileSync(path, 'utf8');

if (!source.includes('type CupCenterFabProps =')) {
  const anchor = "const compName = (key: CompetitionKey) => key === 'champions' ? 'Champions League' : 'Europa League';\n\n";
  if (!source.includes(anchor)) throw new Error('CupCenterFab: props anchor not found');
  source = source.replace(anchor, `${anchor}type CupCenterFabProps = {\n  hideTrigger?: boolean;\n  initialVisible?: boolean;\n  initialCompetition?: CompetitionKey;\n  onDismiss?: () => void;\n};\n\n`);
}

source = source.replace(
  'export default function CupCenterFab() {',
  "export default function CupCenterFab({ hideTrigger = false, initialVisible = false, initialCompetition = 'champions', onDismiss }: CupCenterFabProps = {}) {",
);
source = source.replace('const [visible, setVisible] = useState(false);', 'const [visible, setVisible] = useState(initialVisible);');
source = source.replace("const [competition, setCompetition] = useState<CompetitionKey>('champions');", 'const [competition, setCompetition] = useState<CompetitionKey>(initialCompetition);');

if (!source.includes('const close = () => {')) {
  const openBlock = `  const open = () => {\n    setVisible(true);\n    void load();\n  };\n`;
  if (!source.includes(openBlock)) throw new Error('CupCenterFab: open block not found');
  source = source.replace(openBlock, `${openBlock}\n  const close = () => {\n    setVisible(false);\n    onDismiss?.();\n  };\n`);
}

source = source.replace('onRequestClose={() => setVisible(false)}', 'onRequestClose={close}');
source = source.replace('<Pressable onPress={() => setVisible(false)} hitSlop={12}><Text style={styles.close}>✕</Text></Pressable>', '<Pressable onPress={close} hitSlop={12}><Text style={styles.close}>✕</Text></Pressable>');

const trigger = `      <Pressable\n        accessibilityRole="button"\n        accessibilityLabel="Champions y Europa League"\n        onPress={open}\n        style={({ pressed }) => [styles.fab, pressed && styles.pressed]}\n      >\n        <Text style={styles.fabText}>🏆 COPAS</Text>\n      </Pressable>`;
if (source.includes(trigger)) {
  source = source.replace(trigger, `      {!hideTrigger ? (\n${trigger}\n      ) : null}`);
}

fs.writeFileSync(path, source);
console.log('AJPA Copas: hub abre la competencia seleccionada sin FAB duplicado.');
