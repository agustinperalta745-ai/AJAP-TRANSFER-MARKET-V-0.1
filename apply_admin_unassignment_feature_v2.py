"""Robust one-shot migration for automatic/manual AJPA unassignment."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")


# 1) Runtime bootstrap.
path = "bot.py"
text = read(path)
anchor = "import assignment_history_authority_patch  # noqa: F401,E402\n"
line = "import discord_departure_unassignment_patch  # noqa: F401,E402\n"
if line not in text:
    if anchor not in text:
        raise RuntimeError("bot.py assignment authority anchor missing")
    text = text.replace(anchor, anchor + line, 1)
    write(path, text)
print("OK bot runtime bootstrap")

# 2) Discord pairing requires a club for non-Staff accounts.
path = "mobile_pairing_patch.py"
text = read(path)
if "Necesitás tener un club asignado para vincular AJPA Mobile" not in text:
    marker = "            # Critical: the code must be created in the exact same SQLite file\n"
    if marker not in text:
        raise RuntimeError("mobile pairing marker missing")
    guard = '''            club = runtime.club_de(interaction.user.id)\n            if not is_staff and not club:\n                await interaction.response.send_message(\n                    "⚠️ Necesitás tener un club asignado para vincular AJPA Mobile.",\n                    ephemeral=True,\n                )\n                return\n\n'''
    text = text.replace(marker, guard + marker, 1)
    duplicate = '''            # Keep this informational field based on the Discord guild where the\n            # manager executed the command; it does not affect pairing storage.\n            club = runtime.club_de(interaction.user.id)\n            embed = discord.Embed(\n'''
    replacement = '''            # Keep this informational field based on the Discord guild where the\n            # manager executed the command; it does not affect pairing storage.\n            embed = discord.Embed(\n'''
    if duplicate not in text:
        raise RuntimeError("mobile pairing duplicate club marker missing")
    text = text.replace(duplicate, replacement, 1)
    write(path, text)
print("OK pairing guard")

# 3) Mobile Staff backend endpoint.
path = "mobile_parity_api_patch.py"
text = read(path)
if "import club_access_revocation as access" not in text:
    if "import sqlite3\n" not in text or "import mobile_read_api\n" not in text:
        raise RuntimeError("mobile parity import anchors missing")
    text = text.replace("import sqlite3\n", "import re\nimport sqlite3\n", 1)
    text = text.replace(
        "import mobile_read_api\n",
        "import club_access_revocation as access\nimport mobile_read_api\n",
        1,
    )
start = text.index("    def post(self):")
end = text.index("    handler.do_GET = get;", start)
post_block = '''    def post(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        unassign_match = re.fullmatch(r"/api/v1/admin/assignments/(\\d+)/unassign", path)
        if path != "/api/v1/admin/market" and not unassign_match:
            return original_post(self)

        conn = None
        try:
            if unassign_match:
                user_id = int(unassign_match.group(1))
                with mobile_write_api.write_db() as conn:
                    mobile_write_api.ensure_schema(conn)
                    session = _staff_session(self.headers, conn)
                    result = access.unassign_user_in_conn(
                        conn,
                        user_id,
                        actor_id=int(session["user_id"]),
                        source="ADMIN_MOBILE",
                        queue_discord=True,
                    )
                    if not result.get("club"):
                        raise mobile_write_api.ApiFailure(
                            "La asignación ya no existe.", HTTPStatus.NOT_FOUND
                        )
                    conn.commit()
                    self._json({
                        "ok": True,
                        "user_id": str(user_id),
                        "club": result["club"],
                        "sessions_revoked": result.get("sessions_revoked", 0),
                        "message": (
                            f"{result['club']} quedó libre y la vinculación de AJPA Mobile "
                            "del usuario fue invalidada."
                        ),
                    })
                    return

            payload = mobile_write_api._read_json(self)
            with mobile_write_api.write_db() as conn:
                mobile_write_api.ensure_schema(conn)
                session = _staff_session(self.headers, conn)
                opened = payload.get("open")
                if not isinstance(opened, bool):
                    raise mobile_write_api.ApiFailure("Indicá el nuevo estado del mercado.")
                result = set_market_state(conn, session, opened)
                conn.commit()
                self._json(result)
                return
        except mobile_write_api.ApiFailure as exc:
            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    pass
            self._json({"error": "request", "message": exc.message}, exc.status)
        except Exception as exc:
            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    pass
            print(f"AJPA mobile parity POST error: {type(exc).__name__}: {exc}")
            self._json(
                {"error": "internal_error", "message": "No se pudo completar la operación."},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )
'''
text = text[:start] + post_block + text[end:]
write(path, text)
print("OK Staff unassignment HTTP endpoint")

# 4) App API client: destructive endpoint + global token clear on 401.
path = "mobile/src/api.ts"
text = read(path)
if "response.status === 401" not in text:
    marker = "  if (!response.ok) {\n    throw {\n"
    replacement = "  if (!response.ok) {\n    if (response.status === 401) {\n      sessionToken = '';\n      await clearStoredSession();\n    }\n    throw {\n"
    if marker not in text:
        raise RuntimeError("api.ts response error marker missing")
    text = text.replace(marker, replacement, 1)
if "export function unassignAdminAssignment" not in text:
    marker = "export function setAdminMarketOpen(open: boolean) {\n"
    function = '''export function unassignAdminAssignment(userId: string) {
  return apiRequest<{ ok: boolean; user_id: string; club: string; sessions_revoked: number; message: string }>(
    `/api/v1/admin/assignments/${encodeURIComponent(userId)}/unassign`,
    { method: 'POST', body: '{}' },
  );
}

'''
    if marker not in text:
        raise RuntimeError("api.ts Staff market marker missing")
    text = text.replace(marker, function + marker, 1)
write(path, text)
print("OK app API mutation + 401 unlink")

# 5) OTA transform: import mutation and render the red button on Asignaciones.
path = "mobile/scripts/apply-discord-menu-parity.mjs"
text = read(path)
if "unassignAdminAssignment" not in text:
    market_idx = text.index("  setAdminMarketOpen,")
    session_idx = text.index("  setSessionToken,", market_idx)
    insert_at = session_idx + len("  setSessionToken,")
    text = text[:insert_at] + r"\n  unassignAdminAssignment," + text[insert_at:]

start = text.index("  const assignmentsScreen = (")
end_marker = "\n\n`;\n\nui = ui.replace(marker"
end = text.index(end_marker, start)
assignments_block = '''  const confirmAdminUnassign = (item: AdminAssignment) => {
    Alert.alert(
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
    );
  };

  const assignmentsScreen = (
    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl}>
      <Title eyebrow="STAFF" title="Asignaciones" subtitle="Clubes vinculados a Discord. Desasignar también invalida el acceso de esa cuenta a la app." />
      {assignments.length === 0 ? <View style={s.card}><Text style={s.muted}>No hay clubes asignados.</Text></View> : null}
      {assignments.map((item) => (
        <View style={s.card} key={item.user_id}>
          <Text style={s.playerName}>{item.club}</Text>
          <Text style={s.muted}>Discord ID: {item.user_id}</Text>
          <View style={s.actionRow}>
            <Button
              label="DESASIGNAR EQUIPO"
              kind="red"
              disabled={busy}
              onPress={() => confirmAdminUnassign(item)}
            />
          </View>
        </View>
      ))}
    </ScrollView>
  );'''
text = text[:start] + assignments_block + text[end:]
write(path, text)
print("OK OTA Asignaciones destructive button")

print("AJPA unassignment v2 migration complete")
