import discord
from discord.ext import commands, tasks
from discord.ui import Select, View, Button
import os
from datetime import datetime
import asyncio

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

# Klíčové role (5 KRITICKÝCH)
REQUIRED_ROLES = {
    "💚 Healer": True,
    "🎵 Swordsinger": True,
    "🌟 Buffer": True,
    "💃 Bladedance": True,
    "⚔️ Damage Dealers": True,
}

# Progressive Role Requirements (Varianta C)
ROLE_REQUIREMENTS = {
    5: 1,   # 5 hráčů: min 1 klíčová role
    6: 2,   # 6 hráčů: min 2 klíčové role
    7: 3,   # 7 hráčů: min 3 klíčové role
    8: 4,   # 8 hráčů: min 4 klíčové role
    9: 5,   # 9 hráčů: všech 5 klíčových rolí
}

party_data = {
    "lokace": None,
    "cas_timestamp": None,
    "sloty": {role: [] for role in ROLE_SLOTS},
    "msg_id": None,
    "notif_msg_id": None,
    "founder_id": None,
    "completion_msg_ids": [],
    "is_idle": True,  # ✅ NOVÉ - Flag zda je bot v idle stavu
    "reset_task": None,  # ✅ NOVÉ - Ukazatel na běžící reset task
}


def count_filled_required_roles():
    """Spočítá kolik klíčových rolí je obsazeno"""
    count = 0
    for role in REQUIRED_ROLES.keys():
        if len(party_data["sloty"][role]) > 0:
            count += 1
    return count


def get_total_members():
    """Spočítá celkem hráčů v partě"""
    return sum(len(members) for members in party_data["sloty"].values())


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

        # PROGRESSIVE ROLE REQUIREMENT CHECK
        total = get_total_members()
        current_required = ROLE_REQUIREMENTS.get(total + 1, 0)  # +1 protože se právě připojuje
        
        if total + 1 >= 5 and current_required > 0:
            filled_required = count_filled_required_roles()
            is_required_role = role in REQUIRED_ROLES
            
            # Pokud se připojuje na NON-klíčovou roli a už je máme dost
            if not is_required_role and filled_required < current_required:
                missing_roles = [r for r in REQUIRED_ROLES.keys() if len(party_data["sloty"][r]) == 0]
                missing_text = ", ".join(missing_roles)
                await interaction.response.send_message(
                    f"❌ Nemůžeš se přihlásit!\n\n"
                    f"Parta potřebuje klíčové role.\n"
                    f"Obsazeno klíčových: {filled_required}/{current_required}\n"
                    f"Chybí: {missing_text}",
                    ephemeral=True
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
    async def leave_button(self, interaction: discord.Interaction, button: Button):
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
    async def new_party_button(self, interaction: discord.Interaction, button: Button):
        """Tlačítko pro vytvoření nové farmy - zobrazí výběr lokace"""
        await interaction.response.defer()

        guild = bot.get_guild(SERVER_ID)
        channel = guild.get_channel(CHANNEL_ID) if guild else None

        if not channel:
            await interaction.followup.send("❌ Kanál nenalezen!", ephemeral=True)
            return

        embed = discord.Embed(
            title="🌍 Vyber lokaci pro novou farmu",
            description="Kde chceš farmit?",
            color=0x0099FF,
        )
        for emoji_lokace in LOKACE.keys():
            embed.add_field(name="•", value=emoji_lokace, inline=True)

        view = View()
        view.add_item(LokaceSelect())

        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


class IdleView(View):
    """View pro idle stav - jen tlačítko 'Nová farma'"""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Nová farma",
        style=discord.ButtonStyle.blurple,
        custom_id="btn_new_party_idle",
    )
    async def new_party_button(self, interaction: discord.Interaction, button: Button):
        """Tlačítko pro vytvoření nové farmy z idle stavu"""
        await interaction.response.defer()

        guild = bot.get_guild(SERVER_ID)
        channel = guild.get_channel(CHANNEL_ID) if guild else None

        if not channel:
            await interaction.followup.send("❌ Kanál nenalezen!", ephemeral=True)
            return

        embed = discord.Embed(
            title="🌍 Vyber lokaci pro novou farmu",
            description="Kde chceš farmit?",
            color=0x0099FF,
        )
        for emoji_lokace in LOKACE.keys():
            embed.add_field(name="•", value=emoji_lokace, inline=True)

        view = View()
        view.add_item(LokaceSelect())

        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


async def schedule_party_reset():
    """✅ NOVÉ - Naplánuje reset party po 60 minutách"""
    
    # Zruš starý task pokud existuje
    if party_data["reset_task"] is not None:
        party_data["reset_task"].cancel()
        print("⏳ Starý reset task zrušen")
    
    # Vytvoř nový task
    async def reset_after_delay():
        try:
            print("⏳ Reset party za 60 minut...")
            await asyncio.sleep(60 * 60)  # 60 minut
            await reset_to_idle_state()
        except asyncio.CancelledError:
            print("⏳ Reset task byl zrušen")
    
    party_data["reset_task"] = asyncio.create_task(reset_after_delay())


async def reset_to_idle_state():
    """✅ NOVÉ - Resetuje party do idle stavu"""
    guild = bot.get_guild(SERVER_ID)
    channel = guild.get_channel(CHANNEL_ID) if guild else None

    if not channel:
        print("❌ Kanál nenalezen!")
        return

    print("🔄 Resetuji party do idle stavu...")

    # Smaž všechny completion zprávy
    for msg_id in party_data["completion_msg_ids"]:
        try:
            msg = await channel.fetch_message(msg_id)
            await msg.delete()
        except Exception as e:
            print(f"⚠️ Chyba při mazání completion zprávy: {e}")

    # Resetuj party data
    party_data["lokace"] = None
    party_data["cas_timestamp"] = None
    party_data["sloty"] = {role: [] for role in ROLE_SLOTS}
    party_data["founder_id"] = None
    party_data["completion_msg_ids"] = []
    party_data["is_idle"] = True
    party_data["reset_task"] = None

    # Aktualizuj main embed na idle verzi
    if party_data["msg_id"]:
        try:
            msg = await channel.fetch_message(party_data["msg_id"])
            
            idle_embed = discord.Embed(
                title="😴 Nudím se mi",
                description="Nikdo nic neskládá, já se nudím, pojď zahájit novou farmu!",
                color=0x808080,
            )
            
            await msg.edit(embed=idle_embed, view=IdleView())
            print("✅ Party resetována do idle stavu")
        except Exception as e:
            print(f"⚠️ Chyba při editaci party embedu: {e}")


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

    # Vymaž staré completion zprávy
    for msg_id in party_data["completion_msg_ids"]:
        try:
            old_completion = await channel.fetch_message(msg_id)
            await old_completion.delete()
        except Exception as e:
            print(f"⚠️ Chyba při mazání completion zprávy: {e}")

    # ✅ NOVÉ - Zruš starý reset task
    if party_data["reset_task"] is not None:
        party_data["reset_task"].cancel()
        print("⏳ Reset task zrušen")

    # Nastav novou farmu
    party_data["lokace"] = lokace
    party_data["cas_timestamp"] = int(datetime.now().timestamp())
    party_data["sloty"] = {role: [] for role in ROLE_SLOTS}
    party_data["founder_id"] = interaction.user.id
    party_data["completion_msg_ids"] = []
    party_data["is_idle"] = False  # ✅ NOVÉ

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
    """Aktualizuje zprávu s party obsazením - NOVÁ MODULÁRNÍ STRUKTURA"""
    guild = bot.get_guild(SERVER_ID)
    channel = guild.get_channel(CHANNEL_ID) if guild else None

    if not channel or not party_data["lokace"]:
        return

    total = get_total_members()
    cas_display = f"<t:{party_data['cas_timestamp']}:f>"

    # Vytvořit hlavní embed
    embed = discord.Embed(
        title="🎮 Společná party farma",
        description=(
            f"**Lokace:** {party_data['lokace']}\n"
            f"**Zahájena:** {cas_display}\n\n"
            "Pravidla: Dělba dropu dle CP pravidel, dbej pokynu party leadera, komunikuj na discordu, buď připraven.\n\n"
            f"**Obsazení: {total}/9**"
        ),
        color=0x0099FF,
    )

    # STAV PARTY SEKCE
    filled_required = count_filled_required_roles()
    missing_required = [r for r in REQUIRED_ROLES.keys() if len(party_data["sloty"][r]) == 0]

    if missing_required:
        warning_text = "🚨 **CHYBĚJÍCÍ KLÍČOVÉ ROLE:**\n"
        for role in missing_required:
            warning_text += f"❌ {role}\n"
        embed.add_field(name="⚠️ STAV PARTY", value=warning_text, inline=False)
    else:
        embed.add_field(
            name="✅ PARTY READY",
            value="Všechny klíčové role jsou obsazeny! ✨",
            inline=False
        )

    # OBSAZENÉ ROLE SEKCE (jen role co MAJÍ hráče)
    occupied_roles = []
    for role, max_slot in ROLE_SLOTS.items():
        members = party_data["sloty"][role]
        if len(members) > 0:
            member_text = ", ".join(m.mention for m in members)
            occupied_roles.append(f"{role} ({len(members)}/{max_slot}) - {member_text}")

    if occupied_roles:
        occupied_text = "\n".join(occupied_roles)
        embed.add_field(name="✅ OBSAZENÉ ROLE", value=occupied_text, inline=False)
    else:
        embed.add_field(name="✅ OBSAZENÉ ROLE", value="Žádné role zatím obsazeny", inline=False)

    # ZBÝVAJÍCÍ SLOTY SEKCE (jen volné role)
    remaining_roles = []
    for role, max_slot in ROLE_SLOTS.items():
        members = party_data["sloty"][role]
        if len(members) == 0:
            remaining_roles.append(f"{role} (0/{max_slot})")
        elif len(members) < max_slot:
            remaining_roles.append(f"{role} ({len(members)}/{max_slot})")

    if remaining_roles:
        remaining_text = "\n".join(remaining_roles)
        embed.add_field(name="📋 ZBÝVAJÍCÍ SLOTY", value=remaining_text, inline=False)

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

    # FULL PARTY SIGNALIZACE
    if total == 9:
        if not missing_required:  # Všechny klíčové role jsou OK
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
            completion_msg = await channel.send(embed=full_embed)
            party_data["completion_msg_ids"].append(completion_msg.id)
            
            # ✅ NOVÉ - Naplánuj reset za 60 minut
            await schedule_party_reset()
        else:
            missing_text = ", ".join(missing_required)
            warning_embed = discord.Embed(
                title="⚠️ Party (9/9) ale chybí role!",
                description=f"Parta je plná, ale chybí: {missing_text}\nNěkdo se musí odhlásit a nahradit jej!",
                color=0xFF9900,
            )
            completion_msg = await channel.send(embed=warning_embed)
            party_data["completion_msg_ids"].append(completion_msg.id)


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
