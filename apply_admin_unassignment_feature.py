"""One-shot source migration for AJPA automatic/manual club unassignment."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def replace(path: str, old: str, new: str, label: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if old not in text:
        if new in text:
            print(f"SKIP {label}: already applied")
            return
        raise RuntimeError(f"Missing marker for {label} in {path}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"OK {label}")


# Runtime: install Discord leave reconciliation after the assignment authority layer.
replace(
    "bot.py",
    "import assignment_history_authority_patch  # noqa: F401,E402\n",
    "import assignment_history_authority_patch  # noqa: F401,E402\nimport discord_departure_unassignment_patch  # noqa: F401,E402\n",
    "Discord departure cleanup bootstrap",
)

# Pairing: a non-Staff account without a club cannot immediately re-link after Staff unassigns it.
pair_path = ROOT / "mobile_pairing_patch.py"
pair = pair_path.read_text(encoding="utf-8")
old_pair = '''            is_staff = bool(\n                isinstance(interaction.user, discord.Member)\n                and interaction.user.guild_permissions.administrator\n            )\n\n            # Critical: the code must be created in the exact same SQLite file\n'''
new_pair = '''            is_staff = bool(\n                isinstance(interaction.user, discord.Member)\n                and interaction.user.guild_permissions.administrator\n            )\n            club = runtime.club_de(interaction.user.id)\n            if not is_staff and not club:\n                await interaction.response.send_message(\n                    "⚠️ Necesitás tener un club asignado para vincular AJPA Mobile.",\n                    ephemeral=True,\n                )\n                return\n\n            # Critical: the code must be created in the exact same SQLite file\n'''
if old_pair in pair:
    pair = pair.replace(old_pair, new_pair, 1)
elif new_pair not in pair:
    raise RuntimeError("Missing pairing access marker")
pair = pair.replace(
    '''            # Keep this informational field based on the Discord guild where the\n            # manager executed the command; it does not affect pairing storage.\n            club = runtime.club_de(interaction.user.id)\n            embed = discord.Embed(\n''',
    '''            # Keep this informational field based on the Discord guild where the\n            # manager executed the command; it does not affect pairing storage.\n            embed = discord.Embed(\n''',
    1,
)
pair_path.write_text(pair, encoding="utf-8")
print("OK Mobile pairing requires club for non-Staff")

# Mobile backend: expose a Staff-only destructive unassignment endpoint.
parity_path = ROOT / "mobile_parity_api_patch.py"
parity = parity_path.read_text(encoding="utf-8")
if "import club_access_revocation as access" not in parity:
    parity = parity.replace(
        "import sqlite3\n",
        "import re\nimport sqlite3\n",
        1,
    ).replace(
        "import mobile_read_api\n",
        "import club_access_revocation as access\nimport mobile_read_api\n",
        1,
    )
start = parity.index("    def post(self):")
end = parity.index("    handler.do_GET = get;", start)
new_post = '''    def post(self):\n        path = urlparse(self.path).path.rstrip("/") or "/"\n        unassign_match = re.fullmatch(r"/api/v1/admin/assignments/(\\d+)/unassign", path)\n        if path != "/api/v1/admin/market" and not unassign_match:\n            return original_post(self)\n\n        conn = None\n        try:\n            if unassign_match:\n                user_id = int(unassign_match.group(1))\n                with mobile_write_api.write_db() as conn:\n                    mobile_write_api.ensure_schema(conn)\n                    session = _staff_session(self.headers, conn)\n                    result = access.unassign_user_in_conn(\n                        conn,\n                        user_id,\n                        actor_id=int(session["user_id"]),\n                        source="ADMIN_MOBILE",\n                        queue_discord=True,\n                    )\n                    if not result.get("club"):\n                        raise mobile_write_api.ApiFailure(\n                            "La asignación ya no existe.", HTTPStatus.NOT_FOUND\n                        )\n                    conn.commit()\n                    self._json({\n                        "ok": True,\n                        "user_id": str(user_id),\n                        "club": result["club"],\n                        "sessions_revoked": result.get("sessions_revoked", 0),\n                        "message": (\n                            f"{result['club']} quedó libre y la vinculación de AJPA Mobile "\n                            "del usuario fue invalidada."\n                        ),\n                    })\n                    return\n\n            payload = mobile_write_api._read_json(self)\n            with mobile_write_api.write_db() as conn:\n                mobile_write_api.ensure_schema(conn)\n                session = _staff_session(self.headers, conn)\n                opened = payload.get("open")\n                if not isinstance(opened, bool):\n                    raise mobile_write_api.ApiFailure("Indicá el nuevo estado del mercado.")\n                result = set_market_state(conn, session, opened)\n                conn.commit()\n                self._json(result)\n                return\n        except mobile_write_api.ApiFailure as exc:\n            if conn is not None:\n                try:\n                    conn.rollback()\n                except Exception:\n                    pass\n            self._json({"error": "request", "message": exc.message}, exc.status)\n        except Exception as exc:\n            if conn is not None:\n                try:\n                    conn.rollback()\n                except Exception:\n                    pass\n            print(f"AJPA mobile parity POST error: {type(exc).__name__}: {exc}")\n            self._json(\n                {"error": "internal_error", "message": "No se pudo completar la operación."},\n                HTTPStatus.INTERNAL_SERVER_ERROR,\n            )\n'''
parity = parity[:start] + new_post + parity[end:]
parity_path.write_text(parity, encoding="utf-8")
print("OK Mobile Staff unassignment endpoint")

# Mobile API client: invalidate local storage on any 401 and add the Staff mutation.
api_path = ROOT / "mobile/src/api.ts"
api = api_path.read_text(encoding="utf-8")
old_error = '''  if (!response.ok) {\n    throw {\n      message: String(payload?.message || payload?.error || `La API respondió ${response.status}.`),\n      status: response.status,\n    } satisfies ApiError;\n  }\n'''
new_error = '''  if (!response.ok) {\n    if (response.status === 401) {\n      sessionToken = '';\n      await clearStoredSession();\n    }\n    throw {\n      message: String(payload?.message || payload?.error || `La API respondió ${response.status}.`),\n      status: response.status,\n    } satisfies ApiError;\n  }\n'''
if old_error in api:
    api = api.replace(old_error, new_error, 1)
elif new_error not in api:
    raise RuntimeError("Missing global 401 marker in mobile api.ts")

assignment_fn = '''export async function fetchAdminAssignments(): Promise<AdminAssignment[]> {\n  const result = await apiRequest<{ assignments: AdminAssignment[] }>('/api/v1/admin/assignments');\n  return result.assignments;\n}\n'''
assignment_new = assignment_fn + '''\nexport function unassignAdminAssignment(userId: string) {\n  return apiRequest<{ ok: boolean; user_id: string; club: string; sessions_revoked: number; message: string }>(\n    `/api/v1/admin/assignments/${encodeURIComponent(userId)}/unassign`,\n    { method: 'POST', body: '{}' },\n  );\n}\n'''
if assignment_fn in api and "unassignAdminAssignment" not in api:
    api = api.replace(assignment_fn, assignment_new, 1)
elif "unassignAdminAssignment" not in api:
    raise RuntimeError("Missing AdminAssignment API marker")
api_path.write_text(api, encoding="utf-8")
print("OK Mobile API unassignment + global 401 unlink")

# OTA source transformer: turn the existing Asignaciones list into a destructive Staff control.
parity_script_path = ROOT / "mobile/scripts/apply-discord-menu-parity.mjs"
script = parity_script_path.read_text(encoding="utf-8")
old_import = '''  `  sendOffer,\\n  setSessionToken,`,\n  `  sendOffer,\\n  setAdminMarketOpen,\\n  setSessionToken,`,\n'''
new_import = '''  `  sendOffer,\\n  setSessionToken,`,\n  `  sendOffer,\\n  setAdminMarketOpen,\\n  setSessionToken,\\n  unassignAdminAssignment,`,\n'''
if old_import in script:
    script = script.replace(old_import, new_import, 1)
elif new_import not in script:
    raise RuntimeError("Missing parity import marker")

old_assignments = '''  const assignmentsScreen = (\n    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl}>\n      <Title eyebrow=\\"STAFF\\" title=\\"Asignaciones\\" subtitle=\\"Asignaciones actuales leídas desde la misma base del bot.\\" />\n      {assignments.length === 0 ? <View style={s.card}><Text style={s.muted}>No hay clubes asignados.</Text></View> : null}\n      {assignments.map((item) => (\n        <View style={s.card} key={item.user_id}>\n          <Text style={s.playerName}>{item.club}</Text>\n          <Text style={s.muted}>Discord ID: {item.user_id}</Text>\n        </View>\n      ))}\n    </ScrollView>\n  );\n\n'''
new_assignments = '''  const confirmAdminUnassign = (item: AdminAssignment) => {\n    Alert.alert(\n      'Desasignar equipo',\n      '¿Querés liberar ' + item.club + ' del usuario ' + item.user_id + '?\\n\\nSe quitará la asignación y se invalidará su vinculación con AJPA Mobile.',\n      [\n        { text: 'CANCELAR', style: 'cancel' },\n        {\n          text: 'DESASIGNAR',\n          style: 'destructive',\n          onPress: async () => {\n            if (busy) return;\n            setBusy(true);\n            try {\n              const result = await unassignAdminAssignment(item.user_id);\n              setAssignments(await fetchAdminAssignments());\n              await loadAll(true);\n              Alert.alert('Equipo desasignado', result.message || (item.club + ' quedó libre.'));\n            } catch (error) {\n              Alert.alert('No se pudo desasignar', apiError(error));\n            } finally {\n              setBusy(false);\n            }\n          },\n        },\n      ],\n    );\n  };\n\n  const assignmentsScreen = (\n    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl}>\n      <Title eyebrow=\\"STAFF\\" title=\\"Asignaciones\\" subtitle=\\"Clubes vinculados a Discord. Desasignar también invalida el acceso de esa cuenta a la app.\\" />\n      {assignments.length === 0 ? <View style={s.card}><Text style={s.muted}>No hay clubes asignados.</Text></View> : null}\n      {assignments.map((item) => (\n        <View style={s.card} key={item.user_id}>\n          <Text style={s.playerName}>{item.club}</Text>\n          <Text style={s.muted}>Discord ID: {item.user_id}</Text>\n          <View style={s.actionRow}>\n            <Button\n              label=\\"DESASIGNAR EQUIPO\\"\n              kind=\\"red\\"\n              disabled={busy}\n              onPress={() => confirmAdminUnassign(item)}\n            />\n          </View>\n        </View>\n      ))}\n    </ScrollView>\n  );\n\n'''
if old_assignments in script:
    script = script.replace(old_assignments, new_assignments, 1)
elif new_assignments not in script:
    raise RuntimeError("Missing assignments screen marker in parity script")
parity_script_path.write_text(script, encoding="utf-8")
print("OK OTA Asignaciones screen gets Desasignar Equipo")

print("AJPA admin unassignment feature source migration complete")
