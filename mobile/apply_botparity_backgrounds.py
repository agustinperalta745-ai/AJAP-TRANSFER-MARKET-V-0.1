from pathlib import Path

p = Path(__file__).resolve().parent / "src" / "BotParityAppV2.tsx"
s = p.read_text(encoding="utf-8")

if "  ImageBackground,\n" not in s:
    s = s.replace("  Alert,\n", "  Alert,\n  ImageBackground,\n")

session_import = "import { clearStoredSession, loadStoredSession, saveStoredSession } from './session';\n"
bg_imports = (
    "import { BG_INICIO } from './bg_inicio';\n"
    "import { BG_EQUIPOS } from './bg_equipos';\n"
    "import { BG_MERCADO } from './bg_mercado';\n"
    "import { BG_LIBRES } from './bg_libres';\n"
    "import { BG_PERFIL } from './bg_perfil';\n"
)
if "from './bg_inicio'" not in s:
    s = s.replace(session_import, session_import + bg_imports)

map_block = """  const screenBackground = (() => {
    if (screen === 'profile') return BG_PERFIL;
    if (['club', 'roster', 'economy', 'clubValue', 'clubInfo'].includes(screen)) return BG_EQUIPOS;
    if (screen === 'transferibles') return BG_LIBRES;
    if (['market', 'publish', 'clausulazo', 'offers', 'search', 'history'].includes(screen)) return BG_MERCADO;
    return BG_INICIO;
  })();

"""
marker = "  let body: ReactNode = home;\n"
if "const screenBackground" not in s:
    s = s.replace(marker, map_block + marker)

old_main = "      <View style={s.main}>{body}</View>\n"
new_main = """      <View style={s.main}>
        <ImageBackground
          source={{ uri: screenBackground }}
          style={s.screenBackground}
          imageStyle={s.screenBackgroundImage}
          resizeMode="cover"
        >
          <View style={s.screenShade}>{body}</View>
        </ImageBackground>
      </View>
"""
if old_main in s:
    s = s.replace(old_main, new_main)

old_style = "  main: { flex: 1 },\n"
new_style = (
    "  main: { flex: 1 },\n"
    "  screenBackground: { flex: 1 },\n"
    "  screenBackgroundImage: { opacity: 0.88 },\n"
    "  screenShade: { flex: 1, backgroundColor: 'rgba(2,6,10,0.24)' },\n"
)
if "screenBackgroundImage:" not in s:
    s = s.replace(old_style, new_style)

replacements = {
    "panel: '#08121c'": "panel: 'rgba(8,18,28,0.80)'",
    "panel2: '#0b1824'": "panel2: 'rgba(11,24,36,0.80)'",
    "backgroundColor: '#03080d'": "backgroundColor: 'rgba(3,8,13,0.90)'",
    "backgroundColor: '#170b0e'": "backgroundColor: 'rgba(23,11,14,0.86)'",
    "backgroundColor: '#071b12'": "backgroundColor: 'rgba(7,27,18,0.82)'",
    "backgroundColor: '#1b0b0d'": "backgroundColor: 'rgba(27,11,13,0.82)'",
    "backgroundColor: '#091928'": "backgroundColor: 'rgba(9,25,40,0.86)'",
    "backgroundColor: '#05101a'": "backgroundColor: 'rgba(5,16,26,0.88)'",
    "backgroundColor: '#07111a'": "backgroundColor: 'rgba(7,17,26,0.86)'",
    "backgroundColor: '#0a1620'": "backgroundColor: 'rgba(10,22,32,0.86)'",
}
for old, new in replacements.items():
    s = s.replace(old, new)

p.write_text(s, encoding="utf-8")
print("AJPA backgrounds applied to BotParityAppV2")
