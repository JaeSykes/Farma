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

# Lokace s emoji
LOKACE = {
    "🐉 Dragon Valley": "Dragon Valley",
    "🐲 Lair of Antharas": "Lair of Antharas",
    "🕳️ Giant Cave": "Giant Cave",
    "🌱 Seed of Annihilation": "Seed of Annihilation",
    "🏚️ TOP Cata/Necro": "TOP Cata/Necro",
    "⚒️ Forge of Gods": "Forge of Gods",
}

# Role s emoji
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

party_data = {
    "lokace": None,
    "cas": None,
    "sloty": {role: [] for role in ROLE_SLOTS},
    "msg_id": None,
    "notif_msg_id": None,
    "founder_id": None,
}


class LokaceSelect(Select):
    """Výběr lokace pro farmu"""
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
    """Výběr role v partě"""
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

        # Kontrola zda role není plná
        if len(party_data["sloty"][role]) >= ROLE_SLOTS[role]:
            await interaction.response.send_message(
                f"❌ Role **{role}** je již obsazená!", ephemeral=True
            )
            return

        # Odstranění ze všech rolí
        for r, members in party_data["sloty"].items():
            if user in members:
                members.remove(user)

        # Přidání do vybrané role
        party_data["sloty"][role].append(user)
        await interaction.response.send_message(
            f"✅ Přihlášen na roli **{role}**!", ephemeral=True
        )
        await update_party_embed()


class PartyView(View):
    """View s tlačítky pro party"""
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(RoleSelect())

    @discord.ui.button(
        label="Odhlásit se",
        style=discord.ButtonStyle.red,
        custom_id="btn_leave",
    )
    async def leave_button(self, button: Button, interaction: discord.Interaction):
        """Tlačítko pro odhlášení z party"""
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
    async def new_party_button(self, button: Button, interaction: discord.Interaction):
        """Tlačítko pro vytvoření nové farmy - dostupné komukoliv"""
        await interaction.response.defer()

        guild = bot.get_guild(SERVER_ID)
        channel = guild.get_channel(CHANNEL_ID) if guild else None

        if not channel:
            await interaction.followup.send("❌ Kanál nenalezen!", ephemeral=True)
            return

        # Vymaž starou party zprávu
        if party_data["msg_id"] and channel:
            try:
                msg = await channel.fetch_message(party_data["msg_id"])
                await msg.delete()
            except Exception as e:
                print(f"⚠️ Chyba při mazání party zprávy: {e}")

        # Vymaž starou notifikaci
        if party_data["notif_msg_id"] and channel:
            try:
                msg = await channel.fetch_message(party_data["notif_msg_id"])
                await msg.delete()
            except Exception as e:
                print(f"⚠️ Chyba při mazání notifikace: {e}")

        # Reset party
        party_data["sloty"] = {role: [] for role in ROLE_SLOTS}
        party_data["msg_id"] = None
        party_data["notif_msg_id"] = None
        party_data["founder_id"] = None
        party_data["lokace"] = None
        party_data["cas"] = None

        # Zobraz výběr lokace
        embed = discord.Embed(
            title="🌍 Vyber lokaci pro novou farmu",
            description="Kde chceš farmit?",
            color=0x0099FF,
        )
        for emoji_lokace in LOKACE.keys():
            embed.add_field(name="•", value=emoji_lokace, inline=True)

        view = View()
        view.add_item(LokaceSelect())

        await interaction.followup.send(embed=embed, view=view, ephemeral=False)


async def create_new_party(interaction: discord.Interaction, lokace: str):
    """Vytvoří novou farmu s vybranou lokalitou"""
    guild = bot.get_guild(SERVER_ID)
    channel = guild.get_channel(CHANNEL_ID) if guild else None

    if not channel:
        print(f"❌ Kanál nenalezen! ID: {CHANNEL_ID}")
        await interaction.followup.send("❌ Kanál nenalezen!", ephemeral=True)
        return

    # Vymaž starou party zprávu
    if party_data["msg_id"]:
        try:
            old_msg = await channel.fetch_message(party_data["msg_id"])
            await old_msg.delete()
        except Exception as e:
            print(f"⚠️ Chyba při mazání staré party: {e}")

    # Vymaž starou notifikaci
    if party_data["notif_msg_id"]:
        try:
            old_notif = await channel.fetch_message(party_data["notif_msg_id"])
            await old_notif.delete()
        except Exception as e:
            print(f"⚠️ Chyba při mazání staré notifikace: {e}")

    # Nastav novou farmu
    party_data["lokace"] = lokace
    party_data["cas"] = datetime.now().strftime("%d.%m.%Y %H:%M")
    party_data["sloty"] = {role: [] for role in ROLE_SLOTS}
    party_data["founder_id"] = interaction.user.id

    # Notifikace o skládání nové party
    notif_embed = discord.Embed(
        title="🎉 Skládá se nová farm parta",
        description=f"do lokace **{lokace}**\n\nZakladatel: {interaction.user.mention}",
        color=0x00FF00,
    )
    notif_msg = await channel.send(content="@everyone", embed=notif_embed)
    party_data["notif_msg_id"] = notif_msg.id

    await update_party_embed()


async def update_party_embed():
    """Aktualizuje zprávu s party obsazením"""
    guild = bot.get_guild(SERVER_ID)
    channel = guild.get_channel(CHANNEL_ID) if guild else None

    if not channel or not party_data["lokace"]:
        return

    # Spočítej obsazení
    total = sum(len(members) for members in party_data["sloty"].values())

    # Vytvořit embed
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

    # Přidej role s hráči
    for role, max_slot in ROLE_SLOTS.items():
        members = party_data["sloty"][role]
        member_text = ", ".join(m.mention for m in members) if members else "❌ Volné"
        
        embed.add_field(
            name=f"{role} ({len(members)}/{max_slot})",
            value=member_text,
            inline=False,
        )

    embed.set_footer(text="Klikni na 'Nová farma' pro reset")

    # Aktualizuj nebo vytvoř novou zprávu
    if party_data["msg_id"]:
        try:
            msg = await channel.fetch_message(party_data["msg_id"])
            await msg.edit(embed=embed, view=PartyView())
        except Exception as e:
            print(f"⚠️ Chyba při editaci party: {e}")
            msg = await channel.send(embed=embed, view=PartyView())
            party_data["msg_id"] = msg.id
    else:
        msg = await channel.send(embed=embed, view=PartyView())
        party_data["msg_id"] = msg.id

    # Oznámení když je parta plná
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
    """Spuštění bota"""
    print(f"✅ Bot {bot.user} je online!")
    await bot.tree.sync()


@bot.tree.command(name="farma", description="Spustit party finder pro farmu")
async def farma_cmd(interaction: discord.Interaction):
    """Slash command pro spuštění party finderu"""
    embed = discord.Embed(
        title="🌍 Vyber lokaci pro farmu",
        description="Dostupné lokace:",
        color=0x0099FF,
    )
    for emoji_lokace in LOKACE.keys():
        embed.add_field(name="•", value=emoji_lokace, inline=True)

    view = View()
    view.add_item(LokaceSelect())

    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


@bot.command()
@commands.is_owner()
async def sync(ctx):
    """Resync slash commands (pouze pro vlastníka)"""
    await bot.tree.sync()
    await ctx.send("✅ Slash commands resyncnuté.")


# Spuštění bota
bot.run(os.getenv("DISCORD_TOKEN"))
