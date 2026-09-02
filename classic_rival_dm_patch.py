"""Persistent DM actions shared by bot and mobile-created classic requests."""

from contextlib import closing

import discord

import mobile_classic_rival_api_patch as classic
import mobile_write_api


def request_components(guild_id, request_id):
    return [{"type": 1, "components": [
        {"type": 2, "style": 3 if action == "ACCEPT" else 4, "disabled": False,
         "label": "Aceptar clásico" if action == "ACCEPT" else "Rechazar",
         "custom_id": f"ajpa:classic:{int(guild_id)}:{int(request_id)}:{action}"}
        for action in ("ACCEPT", "REJECT")
    ]}]


class ClassicDMAction(discord.ui.DynamicItem[discord.ui.Button],
                      template=r"ajpa:classic:(?P<guild>[0-9]+):(?P<request>[0-9]+):(?P<action>ACCEPT|REJECT)"):
    def __init__(self, guild_id, request_id, decision):
        self.guild_id = int(guild_id)
        self.request_id = int(request_id)
        self.decision = decision
        spec = request_components(guild_id, request_id)[0]["components"][decision == "REJECT"]
        super().__init__(discord.ui.Button(label=spec["label"], style=discord.ButtonStyle(spec["style"]), custom_id=spec["custom_id"]))

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(int(match["guild"]), int(match["request"]), match["action"])

    async def callback(self, interaction):
        import classic_rival_discord_patch as ui

        await interaction.response.defer()
        try:
            # A DM has no interaction.guild: always use the request's guild DB.
            with closing(ui.APP.db_for_guild(self.guild_id)) as conn:
                classic.ensure_schema(conn)
                conn.execute("BEGIN IMMEDIATE")
                try:
                    result, notification = classic._respond_classic(
                        conn, ui._session(interaction.user.id),
                        {"request_id": self.request_id, "decision": self.decision},
                    )
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
            if result["status"] == "ACCEPTED":
                text = f"🔥 **{result['requester_club']} vs {result['target_club']}** ya es un clásico oficial de AJPA."
            else:
                text = f"❌ Rechazaste la propuesta de **{result['requester_club']}**."
            await interaction.edit_original_response(content=text, embed=None, view=None)
            if notification:
                await ui._dm(*notification)
        except mobile_write_api.ApiFailure as exc:
            await interaction.followup.send(f"⚠️ {exc.message}", ephemeral=True)


def request_view(guild_id, request_id):
    view = discord.ui.View(timeout=None)
    for decision in ("ACCEPT", "REJECT"):
        view.add_item(ClassicDMAction(guild_id, request_id, decision))
    return view
