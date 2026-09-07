import fs from 'node:fs';

const file = 'src/CompetitionCycleAdminFab.tsx';
let source = fs.readFileSync(file, 'utf8');

function replaceOnce(before, after, label) {
  if (!source.includes(before)) {
    throw new Error(`GES admin OTA patch: no se encontró ${label}`);
  }
  source = source.replace(before, after);
}

replaceOnce(
  "  const [configSaving, setConfigSaving] = useState(false);",
  "  const [configSaving, setConfigSaving] = useState(false);\n  const [configSaved, setConfigSaved] = useState(false);",
  'estado configSaving',
);

// GET: trust the persisted status returned by the backend.
replaceOnce(
  "      setGesConfig(data);\n      setGesUrl(data.ges_url || '');",
  "      setGesConfig(data);\n      setConfigSaved(Boolean(data.configured));\n      setGesUrl(data.ges_url || '');",
  'estado al cargar configuración',
);

// POST: a successful save is authoritative for the current screen. Do not keep
// the button disabled merely because an older/stale GET raced the POST.
replaceOnce(
  "      setGesConfig(data);\n      setGesUrl(data.ges_url || '');",
  "      const confirmed = { ...data, configured: true };\n      setGesConfig(confirmed);\n      setConfigSaved(true);\n      setGesUrl(data.ges_url || gesUrl.trim());",
  'estado después de guardar configuración',
);

replaceOnce(
  "                setGesConfig(null);\n                setGesUrl('');",
  "                setGesConfig(null);\n                setConfigSaved(false);\n                setGesUrl('');",
  'reset al cambiar de competencia',
);

replaceOnce(
  "    if (!gesConfig?.configured) {\n      Alert.alert('Primero guardá los enlaces', 'Antes de sincronizar, guardá los tres enlaces GES de la competencia actual.');\n      return;\n    }",
  "    if (!configSaved) {\n      Alert.alert('Primero guardá los enlaces', 'Antes de sincronizar, guardá los tres enlaces GES de la competencia actual.');\n      return;\n    }",
  'validación de sincronización',
);

source = source.replace(
  "onChangeText={setGesUrl}",
  "onChangeText={value => { setGesUrl(value); setConfigSaved(false); }}",
);
source = source.replace(
  "onChangeText={setResultsUrl}",
  "onChangeText={value => { setResultsUrl(value); setConfigSaved(false); }}",
);
source = source.replace(
  "onChangeText={setScorersUrl}",
  "onChangeText={value => { setScorersUrl(value); setConfigSaved(false); }}",
);

source = source.replaceAll('gesConfig?.configured && styles.configOk', 'configSaved && styles.configOk');
source = source.replaceAll('gesConfig?.configured\n                          ?', 'configSaved\n                          ?');
source = source.replaceAll('|| !gesConfig?.configured}', '|| !configSaved}');
source = source.replaceAll('|| !gesConfig?.configured) && styles.pressed', '|| !configSaved) && styles.pressed');

// configSaved intentionally does not imply that the config object is non-null
// to TypeScript, so every display-only access keeps a safe fallback.
source = source.replace(
  'result.competition_label || gesConfig.competition_label,',
  "result.competition_label || gesConfig?.competition_label || cycle?.phase_label || 'Competencia actual',",
);
source = source.replace(
  "`✅ Configuración guardada${gesConfig.history?.length ? ` · ${gesConfig.history.length} competencia(s) archivadas/configuradas` : ''}`",
  "`✅ Configuración guardada${(gesConfig?.history?.length ?? 0) > 0 ? ` · ${gesConfig?.history?.length ?? 0} competencia(s) archivadas/configuradas` : ''}`",
);

// The callback now depends on the explicit saved state.
source = source.replace(
  '  }, [gesLoading, loading, configSaving, gesConfig]);',
  '  }, [gesLoading, loading, configSaving, configSaved, gesConfig, cycle?.phase_label]);',
);

if (!source.includes('const [configSaved, setConfigSaved] = useState(false);')) {
  throw new Error('GES admin OTA patch: no se instaló configSaved');
}
if (!source.includes('disabled={gesLoading || loading || configSaving || !configSaved}')) {
  throw new Error('GES admin OTA patch: el botón GES sigue usando el estado viejo');
}
if (source.includes('result.competition_label || gesConfig.competition_label')) {
  throw new Error('GES admin OTA patch: quedó acceso nullable a competition_label');
}
if (source.includes('gesConfig.history?.length')) {
  throw new Error('GES admin OTA patch: quedó acceso nullable a history');
}

fs.writeFileSync(file, source);
console.log('AJPA Mobile: estado guardado GES + botón de sincronización corregidos');
