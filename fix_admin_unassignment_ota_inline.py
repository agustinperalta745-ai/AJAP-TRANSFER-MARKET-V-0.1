"""Make the AJPA Asignaciones destructive action self-contained.

Later visual build transforms may move/drop helper declarations while preserving
the assignment cards. Keeping the confirm/mutation inline avoids that coupling.
"""
from pathlib import Path

path = Path(__file__).resolve().parent / "mobile/scripts/apply-discord-menu-parity.mjs"
text = path.read_text(encoding="utf-8")
old = '''              onPress={() => confirmAdminUnassign(item)}
'''
new = '''              onPress={() => Alert.alert(
                'Desasignar equipo',
                '¿Querés liberar ' + item.club + ' del usuario ' + item.user_id + '?\\n\\nSe quitará la asignación y se invalidará su vinculación con AJPA Mobile.',
                [
                  { text: 'CANCELAR', style: 'cancel' },
                  {
                    text: 'DESASIGNAR',
                    style: 'destructive',
                    onPress: async () => {
                      if (busy) return;
                      setBusy(true);
                      try {
                        const result = await unassignAdminAssignment(item.user_id);
                        setAssignments(await fetchAdminAssignments());
                        await loadAll(true);
                        Alert.alert('Equipo desasignado', result.message || (item.club + ' quedó libre.'));
                      } catch (error) {
                        Alert.alert('No se pudo desasignar', apiError(error));
                      } finally {
                        setBusy(false);
                      }
                    },
                  },
                ],
              )}
'''
if old in text:
    text = text.replace(old, new, 1)
elif "onPress={() => Alert.alert(\n                'Desasignar equipo'" not in text:
    raise RuntimeError("No encontré el botón Desasignar para volverlo autocontenido")
path.write_text(text, encoding="utf-8")
print("AJPA Asignaciones: acción Desasignar autocontenida para todo el pipeline OTA")
