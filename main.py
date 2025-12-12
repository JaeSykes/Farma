import discord
from discord.ext import commands
from discord.ui import Select, View, Button
import os
from datetime import datetime

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# IDs z env (Railway Variables)
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "1448991981765394432"))
SERVER_ID = int(os.getenv("SERVER_ID", "1397286059406000249"))

LOKACE = {
    "Dragon Valley": "Dragon Valley",
    "Lair of Antharas": "Lair of Antharas",
    "Giant Cave": "Giant Cave",
    "Seed of Annihilation": "Seed of Annihilation",
    "TOP Cata/Necro": "TOP Cata/Necro",
    "Forge of Gods": "Forge of Gods",
}

# Role s vybranými emoji
ROLE_SLOTS = {
    "⚔️ Damage Dealers": 4,
    "🛡️ Tank": 1,
    "🎵 Swordsinger": 1,
    "💃 Bladedance": 1,
    "💚 Healer": 1,
    "🔋 Recharge": 1,
    "🌟 Buffer": 1,
    "💀 Debuffer": 1,
    "🎁 Spoil": 1,
}

# Barvy pro role - kategorizované (Damage=Červená, Support=Modrá, Spoil=Žlutá)
ROLE_COLORS = {
    "⚔️ Damage Dealers": 0xE74C3C,  # Pěkný odstín červené
    "🛡️ Tank": 0xC0392B,  # Tmavší červená
    "💀 Debuffer": 0xEC7063,  # Světlejší červená
    "🎵 Swordsinger": 0x3498DB,  # Pěkný odstín modré
    "💃 Bladedance": 0x5DADE2,  # Lehčí modrá
    "💚 Healer": 0x85C1E2,  # Světlá modrá
    "🔋 Recharge": 0x2E86DE,  # Tmavší modrá
    "🌟 Buffer": 0x1F618D,  # Velmi tmavá modrá
    "🎁 Spoil": 0xF4D03F,  # Pěkný odstín žluté
}

party_data = {
    "lokace": None,
    "cas": None,
    "sloty": {role: [] for role in ROLE_SLOTS},
    "msg_id": None,
    "notif_msg_id": None,
    "founder_id": None,  # ID zakladatele
}


class LokaceSelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=lokace, value=lokace)
            for lokace in LOKACE.values()
        ]
        super().__init__(
            placeholder="Vyber lokaci pro farmu...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        lokace_vyber = self.values[0]
        await interaction.response.defer()
        await create_new_party(interaction, lokace_vyber)


class RoleSelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=role, value=role) for role in ROLE_SLOTS.keys()
        ]
        super().__init__(
            placeholder="Vyber si roli v partě...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        role = self.values[0]
        user = interaction.user

        if len(party_data["sloty"][role]) >= ROLE_SLOTS[role]:
            await interaction.response.send_message(
                f"❌ Role **{role}** je již obsazená!", ephemeral=True
            )
            return

        for r, members in party_data["sloty"].items():
            if user in members:
                members.remove(user)

        party_data["sloty"][role].append(user)
        await interaction.response.send_message(
            f"✅ Přihlášen na roli **{role}**!", ephemeral=True
        )
        await update_party_embed()


class PartyView(View):
    def __init__(self, founder_id: int = None):
        super().__init__(timeout=None)
        self.founder_id = founder_id
        self.add_item(RoleSelect())

    @discord.ui.button(
        label="Odhlásit se",
        style=discord.ButtonStyle.red,
        custom_id="btn_leave",
    )
    async def leave_button(
        self, button: Button, interaction: discord.Interaction
    ):
        user = interaction.user
        found = False

        for role, members in party_data["sloty"].items():
            if user in members:
                members.remove(user)
                found = True
                break

        if found:
            await interaction.response.send_message(
                "✅ Odhlášen z party!", ephemeral=True
            )
            await update_party_embed()
        else:
            await interaction.response.send_message(
                "❌ Nejsi v partě!", ephemeral=True
            )

    @discord.ui.button(
        label="Nová farma",
        style=discord.ButtonStyle.blurple,
        custom_id="btn_new_party",
    )
    async def new_party_button(
        self, button: Button, interaction: discord.Interaction
    ):
        # Zkontroluj jestli klikl zakladatel
        if self.founder_id is None or interaction.user.id != self.founder_id:
            await interaction.response.send_message(
                "❌ Jen zakladatel může zahájit novou farmu!", ephemeral=True
            )
            return

        await interaction.response.defer()

        guild = bot.get_guild(SERVER_ID)
        channel = guild.get_channel(CHANNEL_ID) if guild else None

        if party_data["notif_msg_id"] and channel:
            try:
                msg = await channel.fetch_message(party_data["notif_msg_id"])
                await msg.delete()
            except Exception:
                pass

        party_data["sloty"] = {role: [] for role in ROLE_SLOTS}

        embed = discord.Embed(
            title="🌍 Vyber lokaci pro novou farmu",
            description="Kde chceš farmit?",
            color=0x0099FF,
        )
        for lokace in LOKACE.values():
            embed.add_field(name="•", value=lokace, inline=True)

        view = View()
        view.add_item(LokaceSelect())

        await interaction.followup.send(embed=embed, view=view, ephemeral=False)


async def create_new_party(interaction: discord.Interaction, lokace: str):
    guild = bot.get_guild(SERVER_ID)
    channel = guild.get_channel(CHANNEL_ID) if guild else None

    if not channel:
        print(f"❌ Kanál nenalezen! ID: {CHANNEL_ID}")
        return

    if party_data["msg_id"]:
        try:
            old_msg = await channel.fetch_message(party_data["msg_id"])
            await old_msg.delete()
        except Exception:
            pass

    if party_data["notif_msg_id"]:
        try:
            old_notif = await channel.fetch_message(party_data["notif_msg_id"])
            await old_notif.delete()
        except Exception:
            pass

    party_data["lokace"] = lokace
    party_data["cas"] = datetime.now().strftime("%d.%m.%Y %H:%M")
    party_data["sloty"] = {role: [] for role in ROLE_SLOTS}
    party_data["founder_id"] = interaction.user.id  # Uloží ID zakladatele

    notif_embed = discord.Embed(
        title="🎉 Skládá se nová farm parta",
        description=f"do lokace **{lokace}**\n\nZakladatel: {interaction.user.mention}",
        color=0x00FF00,
    )
    notif_msg = await channel.send(content="@everyone", embed=notif_embed)
    party_data["notif_msg_id"] = notif_msg.id

    await update_party_embed()


async def update_party_embed():
    guild = bot.get_guild(SERVER_ID)
    channel = guild.get_channel(CHANNEL_ID) if guild else None

    if not channel or not party_data["lokace"]:
        return

    total = sum(len(members) for members in party_data["sloty"].values())

    embed = discord.Embed(
        title="🎮 Společná party farma",
        description=(
            f"**Lokace:** {party_data['lokace']}\n"
            f"**Zahájena:** {party_data['cas']}\n\n"
            "Rovnoměrná dělba dropu dle CP pravidel\n\n"
            f"**Obsazení: {total}/10**"
        ),
        color=0x0099FF,
    )

    for role, max_slot in ROLE_SLOTS.items():
        members = party_data["sloty"][role]
        member_text = ", ".join(m.mention for m in members) if members else "❌ Volné"
        
        # Barva podle role
        role_color = ROLE_COLORS.get(role, 0x808080)
        
        embed.add_field(
            name=f"{role} ({len(members)}/{max_slot})",
            value=member_text,
            inline=False,
        )

    embed.set_footer(text="Klikni na 'Nová farma' pro reset")

    # Předej founder_id do PartyView
    if party_data["msg_id"]:
        try:
            msg = await channel.fetch_message(party_data["msg_id"])
            await msg.edit(embed=embed, view=PartyView(founder_id=party_data["founder_id"]))
        except Exception:
            msg = await channel.send(embed=embed, view=PartyView(founder_id=party_data["founder_id"]))
            party_data["msg_id"] = msg.id
    else:
        msg = await channel.send(embed=embed, view=PartyView(founder_id=party_data["founder_id"]))
        party_data["msg_id"] = msg.id

    if total == 10:
        participants = " ".join(
            m.mention for members in party_data["sloty"].values() for m in members
        )
        full_embed = discord.Embed(
            title="✅ Parta složena!",
            description=(
                f"Regroup u **Gatekeeper** před portem do **{party_data['lokace']}**\n\n"
                f"Účastníci: {participants}"
            ),
            color=0x00FF00,
        )
        await channel.send(embed=full_embed)


@bot.event
async def on_ready():
    print(f"✅ Bot {bot.user} je online!")
    await bot.tree.sync()


@bot.tree.command(name="farma", description="Spustit party finder pro farmu")
async def farma_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🌍 Vyber lokaci pro farmu",
        description="Dostupné lokace:",
        color=0x0099FF,
    )
    for lokace in LOKACE.values():
        embed.add_field(name="•", value=lokace, inline=True)

    view = View()
    view.add_item(LokaceSelect())

    # Jen zakladatel vidí výběr lokace
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


@bot.command()
@commands.is_owner()
async def sync(ctx):
    await bot.tree.sync()
    await ctx.send("Slash commands resyncnuté.")


bot.run(os.getenv("DISCORD_TOKEN"))
