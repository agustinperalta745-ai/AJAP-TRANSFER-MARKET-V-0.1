import fs from 'node:fs';

const file = 'src/CupCenterFab.tsx';
let cup = fs.readFileSync(file, 'utf8');

cup = cup.replace(
  "import React, { useCallback, useMemo, useState } from 'react';",
  "import React, { useCallback, useEffect, useMemo, useState } from 'react';",
);

const anchor = `  }, []);\n\n  const open = () => {`;
if (!cup.includes('if (visible) void load();')) {
  if (!cup.includes(anchor)) throw new Error('Cup initial-load fix: load/open anchor not found.');
  cup = cup.replace(
    anchor,
    `  }, []);\n\n  useEffect(() => {\n    if (visible) void load();\n  }, [visible, load]);\n\n  const open = () => {`,
  );
}

if (!cup.includes('useEffect') || !cup.includes('if (visible) void load();')) {
  throw new Error('Cup initial-load fix: final validation failed.');
}

fs.writeFileSync(file, cup);
console.log('AJPA Copas: el contenido del bracket ahora carga automáticamente al abrir desde el menú principal.');
