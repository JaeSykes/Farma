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

CHANNEL_ID = int(os.getenv("CHANNEL_ID", "1448991981765394432"))
SERVER_ID = int(os.getenv("SERVER_ID", "1397286059406000249"))

LOKACE = {
    "🐉 Dragon Valley": "Dragon Valley",
    "🐲 Lair of Antharas": "Lair of Antharas",
    "🕳️ Giant Cave": "Giant Cave",
    "🌱 Seed of Annihilation": "Seed of Annihilation",
    "🏚️ TOP Cata/Necro": "TOP Cata/Necro",
    "⚒️ Forge of Gods": "Forge of Gods",
    "👹 Raid boss run": "Raid boss run",
    "🏆 PvP run": "PvP run",
}

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
    "🛠️ Doplním": 1,
}

REQUIRED_ROLES = {
    "🎵 Swordsinger": True,
    "🌟 Buffer": True,
    "💃 Bladedance": True,
    "⚔️ Damage Dealers": True,
}

ROLE_REQUIREMENTS = {
    5: 1,
    6: 2,
    7: 3,
    9: 4,
}

party_data = {
    "lokace": None,
    "cas_timestamp": None,
    "sloty": {role: [] for role in ROLE_SLOTS},
    "msg_id": None,
    "notif_msg_id": None,
    "founder_id": None,
    "completion_msg_ids": [],
    "is_idle": True,
    "timer_start": None,
    "timer_duration": None,
    "is_completed": False,
    "update_lock": asyncio.Lock(),
    "last_embed_update": 0,
}

def count_filled_required_roles():
    count = 0
    for role in REQUIRED_ROLES.keys():
        if len(party_data["sloty"][role]) > 0:
            count += 1
    return count

def get_total_members():
    return sum(len(members) for members in party_data["sloty"].values())

def get_remaining_time():
    if party_data["timer_start"] is None or party_data["timer_duration"] is None:
        return 0
    elapsed = int(datetime.now().timestamp()) - party_data["timer_start"]
    remaining = party_data["timer_duration"] - elapsed
    return max(0, remaining)

def format_timer(seconds):
    minutes = seconds // 60
    secs = seconds % 60
    return f"{minutes}m {secs}s"

class LokaceSelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=lokace, value=lokace)
            for lokace in LOKACE.values()
        ]
        super().__init__(
            placeholder="Vyber lokaci pro parta...",
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
        remaining = get_remaining_time()
        if remaining <= 0 and not party_data["is_idle"]:
            print(f"⏱️ TIMEOUT DETEKOVÁN! Spouštím reset z RoleSelect...")
            await reset_to_idle_state()
            await interaction.response.send_message("❌ Timeout! Parta byla resetována.", ephemeral=True)
            return

        role = self.values[0]
        user = interaction.user

        if len(party_data["sloty"][role]) >= ROLE_SLOTS[role]:
            await interaction.response.send_message(
                f"❌ Role **{role}** je již obsazená!", ephemeral=True
            )
            return

        total = get_total_members()
        current_required = ROLE_REQUIREMENTS.get(total + 1, 0)

        if total + 1 >= 5 and current_required > 0:
            filled_required = count_filled_required_roles()
            is_required_role = role in REQUIRED_ROLES

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

        for r, members in party_data["sloty"].items():
            if user in members:
                members.remove(user)

        party_data["sloty"][role].append(user)
        await interaction.response.send_message(
            f"✅ Přihlášen na roli **{role}**!", ephemeral=True
        )
        await update_party_embed()

class ConfirmNewFarmView(View):
    def __init__(self, interaction: discord.Interaction):
        super().__init__(timeout=30)
        self.interaction = interaction
        self.confirmed = False

    @discord.ui.button(label="✅ Ano, začít parta!", style=discord.ButtonStyle.green, custom_id="confirm_yes")
    async def confirm_yes(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.interaction.user:
            await interaction.response.send_message("❌ Nemáš právo potvrdit tuto akci!", ephemeral=True)
            return

        self.confirmed = True
        await interaction.response.defer()
        embed = discord.Embed(
            title="🌍 Vyber lokaci pro novou parta",
            description="Kde chceš farmit?",
            color=0x0099FF,
        )
        for emoji_lokace in LOKACE.keys():
            embed.add_field(name="•", value=emoji_lokace, inline=True)

        view = View()
        view.add_item(LokaceSelect())

        await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        self.stop()

    @discord.ui.button(label="❌ Ne, zrušit", style=discord.ButtonStyle.red, custom_id="confirm_no")
    async def confirm_no(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.interaction.user:
            await interaction.response.send_message("❌ Nemáš právo zrušit tuto akci!", ephemeral=True)
            return

        await interaction.response.send_message("❌ Zahájení nové party zrušeno.", ephemeral=True)
        self.stop()

ALLOWED_ROLE_IDS = [
    1397286685544284361,  # Friend of CP
    1397286545379033219,  # Nováček
    1398212336111714325,  # Člen
]

class ManagePartyView(View):
    """Správa party - DYNAMICKÉ selecty"""
    def __init__(self, founder_id: int):
        super().__init__(timeout=60)
        self.founder_id = founder_id
        self.selected_player = None
        self.selected_action = None
        self.selected_role = None
        self.message = None  # Budeme upravovat zprávu
        
        # Přidej selecty s callbacky
        self.add_item(self.create_player_select())
        self.add_item(self.create_action_select())

    def create_player_select(self):
        """Vytvoř hráčský select S callbackem"""
        guild = bot.get_guild(SERVER_ID)
        
        if not guild:
            options = [discord.SelectOption(label="Server nenalezen", value="none")]
        else:
            all_members = [
                m for m in guild.members 
                if not m.bot and any(role.id in ALLOWED_ROLE_IDS for role in m.roles)
            ]
            
            if not all_members:
                options = [discord.SelectOption(label="Žádní hráči dostupní", value="none")]
            else:
                options = [
                    discord.SelectOption(label=m.display_name, value=str(m.id))
                    for m in all_members[:25]
                ]

        select = Select(
            placeholder="Vybrat hráče...",
            min_values=0,
            max_values=1,
            options=options,
        )

        async def player_callback(interaction: discord.Interaction):
            if select.values:
                val = select.values[0]
                self.selected_player = int(val) if val != "none" else None
            else:
                self.selected_player = None
            await interaction.response.defer()

        select.callback = player_callback
        return select

    def create_action_select(self):
        """Vytvoř akční select S callbackem - DYNAMICKY aktualizuje View"""
        options = [
            discord.SelectOption(label="✅ Přihlásit", value="add"),
            discord.SelectOption(label="❌ Odhlásit", value="remove"),
            discord.SelectOption(label="↔️ Přesunout na roli", value="move"),
        ]

        select = Select(
            placeholder="Vybrat akci...",
            min_values=0,
            max_values=1,
            options=options,
        )

        async def action_callback(interaction: discord.Interaction):
            if select.values:
                self.selected_action = select.values[0]
            else:
                self.selected_action = None
            
            # DYNAMICKY AKTUALIZUJ VIEW - přidej/odstraň role select
            await self.update_view_for_action(interaction)

        select.callback = action_callback
        return select

    async def update_view_for_action(self, interaction: discord.Interaction):
        """Aktualizuj View na základě vybrané akce - vytvoří NOVÝ View"""
        # ✅ Vytvoř NOVÝ View místo editování starého
        new_view = ManagePartyView(self.founder_id)
        
        # Zkopíruj aktuální výběry do nového View
        new_view.selected_player = self.selected_player
        new_view.selected_action = self.selected_action
        new_view.selected_role = self.selected_role
        new_view.message = self.message
        
        # Přidej role select JEN když je potřeba
        if new_view.selected_action in ["add", "move"]:
            new_view.add_item(new_view.create_role_select())
        
        # Aktualizuj zprávu s NOVÝM View
        if new_view.message:
            try:
                await new_view.message.edit(view=new_view)
            except Exception as e:
                print(f"⚠️ Chyba při editování zprávy: {e}")
        
        await interaction.response.defer()

    def create_role_select(self):
        """Vytvoř roli select S callbackem"""
        options = [
            discord.SelectOption(label=role, value=role) for role in ROLE_SLOTS.keys()
        ]

        select = Select(
            placeholder="Vybrat roli...",
            min_values=0,
            max_values=1,
            options=options,
        )

        async def role_callback(interaction: discord.Interaction):
            if select.values:
                self.selected_role = select.values[0]
            else:
                self.selected_role = None
            await interaction.response.defer()

        select.callback = role_callback
        return select

    @discord.ui.button(label="✅ Provést akci", style=discord.ButtonStyle.green, custom_id="btn_manage_execute")
    async def execute_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.founder_id:
            await interaction.response.send_message("❌ Jen zakladatel party!", ephemeral=True)
            return

        # Kontrola co je vybráno
        if not self.selected_player or not self.selected_action:
            await interaction.response.send_message(
                "❌ Vyberte hráče a akci!", 
                ephemeral=True
            )
            return

        if self.selected_action in ["add", "move"] and not self.selected_role:
            await interaction.response.send_message(
                "❌ Vyberte roli!", 
                ephemeral=True
            )
            return

        guild = bot.get_guild(SERVER_ID)
        if not guild:
            await interaction.response.send_message("❌ Server nenalezen!", ephemeral=True)
            return

        player = guild.get_member(self.selected_player)
        if not player:
            await interaction.response.send_message("❌ Hráč nenalezen!", ephemeral=True)
            return

        # ODSTRANIT
        if self.selected_action == "remove":
            found = False
            for r, members in party_data["sloty"].items():
                if player in members:
                    members.remove(player)
                    found = True
                    break
            
            if found:
                await interaction.response.send_message(
                    f"✅ {player.mention} odhlášen z party!", 
                    ephemeral=True
                )
                await update_party_embed()
            else:
                await interaction.response.send_message(
                    f"❌ {player.mention} není v partě!", 
                    ephemeral=True
                )

        # PŘIDAT
        elif self.selected_action == "add":
            if len(party_data["sloty"][self.selected_role]) >= ROLE_SLOTS[self.selected_role]:
                await interaction.response.send_message(
                    f"❌ Role **{self.selected_role}** je plná!", 
                    ephemeral=True
                )
                return

            # Odstraň hráče z ostatních rolí
            for r, members in party_data["sloty"].items():
                if player in members:
                    members.remove(player)

            party_data["sloty"][self.selected_role].append(player)
            await interaction.response.send_message(
                f"✅ {player.mention} přihlášen na **{self.selected_role}**!", 
                ephemeral=True
            )
            await update_party_embed()

        # PŘESUNOUT
        elif self.selected_action == "move":
            found = False
            for r, members in party_data["sloty"].items():
                if player in members:
                    members.remove(player)
                    found = True
                    break

            if not found:
                await interaction.response.send_message(
                    f"❌ {player.mention} není v partě!", 
                    ephemeral=True
                )
                return

            if len(party_data["sloty"][self.selected_role]) >= ROLE_SLOTS[self.selected_role]:
                await interaction.response.send_message(
                    f"❌ Role **{self.selected_role}** je plná!", 
                    ephemeral=True
                )
                return

            party_data["sloty"][self.selected_role].append(player)
            await interaction.response.send_message(
                f"✅ {player.mention} přesunut na **{self.selected_role}**!", 
                ephemeral=True
            )
            await update_party_embed()

class PartyView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(RoleSelect())

    @discord.ui.button(label="Odhlásit se", style=discord.ButtonStyle.red, custom_id="btn_leave")
    async def leave_button(self, interaction: discord.Interaction, button: Button):
        remaining = get_remaining_time()
        if remaining <= 0 and not party_data["is_idle"]:
            print(f"⏱️ TIMEOUT DETEKOVÁN! Spouštím reset z leave...")
            await reset_to_idle_state()
            await interaction.response.send_message("❌ Timeout! Parta byla resetována.", ephemeral=True)
            return

        user = interaction.user
        found = False

        for role, members in party_data["sloty"].items():
            if user in members:
                members.remove(user)
                found = True
                break

        if found:
            await interaction.response.send_message("✅ Odhlášen z party!", ephemeral=True)
            await update_party_embed()
        else:
            await interaction.response.send_message("❌ Nejsi v partě!", ephemeral=True)

    @discord.ui.button(label="Spravovat party", style=discord.ButtonStyle.gray, custom_id="btn_manage_party")
    async def manage_party_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != party_data["founder_id"]:
            await interaction.response.send_message("❌ Jen zakladatel party!", ephemeral=True)
            return

        manage_view = ManagePartyView(interaction.user.id)
        embed = discord.Embed(
            title="⚙️ Správa Party",
            description="Vyberte hráče a akci.",
            color=0x00FF00,
        )
        msg = await interaction.response.send_message(embed=embed, view=manage_view, ephemeral=True)
        manage_view.message = msg

    @discord.ui.button(label="Nová parta", style=discord.ButtonStyle.blurple, custom_id="btn_new_party")
    async def new_party_button(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(
            title="⚠️ Jste si jistý?",
            description="Chcete opravdu zahájit **novou parta**?\n\nStará parta bude resetována.",
            color=0xFFAA00,
        )

        confirm_view = ConfirmNewFarmView(interaction)
        await interaction.response.send_message(embed=embed, view=confirm_view, ephemeral=True)

class IdleView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Nová parta", style=discord.ButtonStyle.blurple, custom_id="btn_new_party_idle")
    async def new_party_button(self, interaction: discord.Interaction, button: Button):
        embed = discord.Embed(
            title="⚠️ Jste si jistý?",
            description="Chcete opravdu zahájit **novou parta**?",
            color=0xFFAA00,
        )

        confirm_view = ConfirmNewFarmView(interaction)
        await interaction.response.send_message(embed=embed, view=confirm_view, ephemeral=True)

async def reset_to_idle_state():
    guild = bot.get_guild(SERVER_ID)
    channel = guild.get_channel(CHANNEL_ID) if guild else None

    if not channel:
        print("❌ Kanál nenalezen!")
        return

    print("🔄 RESET: Resetuji party...")

    if party_data["notif_msg_id"]:
        try:
            notif_msg = await channel.fetch_message(party_data["notif_msg_id"])
            await notif_msg.delete()
            print("✅ RESET: Notifikace smazána")
        except Exception as e:
            print(f"⚠️ RESET: Notifikace chyba: {e}")

    for msg_id in party_data["completion_msg_ids"]:
        try:
            msg = await channel.fetch_message(msg_id)
            await msg.delete()
        except Exception as e:
            print(f"⚠️ RESET: Completion chyba: {e}")

    idle_embed = discord.Embed(
        title="😴 Nudím se",
        description="Nikdo nic neskládá, já se nudím, pojď založit novou parta!",
        color=0x808080,
    )

    if party_data["msg_id"]:
        try:
            msg = await channel.fetch_message(party_data["msg_id"])
            await msg.edit(embed=idle_embed, view=IdleView())
            print("✅ RESET: Zpráva změněna na IDLE")
        except discord.NotFound:
            msg = await channel.send(embed=idle_embed, view=IdleView())
            party_data["msg_id"] = msg.id
            print("✅ RESET: Nová IDLE zpráva vytvořena")
        except Exception as e:
            print(f"❌ RESET: Kritická chyba: {e}")

    party_data["is_idle"] = True
    party_data["lokace"] = None
    party_data["cas_timestamp"] = None
    party_data["sloty"] = {role: [] for role in ROLE_SLOTS}
    party_data["founder_id"] = None
    party_data["notif_msg_id"] = None
    party_data["completion_msg_ids"] = []
    party_data["is_completed"] = False
    party_data["timer_start"] = None
    party_data["timer_duration"] = None
    party_data["last_embed_update"] = 0

    print("✅ RESET: Hotovo!")

async def create_new_party(interaction: discord.Interaction, lokace: str):
    guild = bot.get_guild(SERVER_ID)
    channel = guild.get_channel(CHANNEL_ID) if guild else None

    if not channel:
        await interaction.followup.send("❌ Kanál nenalezen!", ephemeral=True)
        return

    old_msg_id = party_data["msg_id"]
    old_notif_id = party_data["notif_msg_id"]
    old_completion_ids = party_data["completion_msg_ids"].copy()

    party_data["timer_start"] = int(datetime.now().timestamp())
    party_data["timer_duration"] = 45 * 60
    party_data["last_embed_update"] = 0
    party_data["is_idle"] = False
    party_data["lokace"] = lokace
    party_data["cas_timestamp"] = int(datetime.now().timestamp())
    party_data["sloty"] = {role: [] for role in ROLE_SLOTS}
    party_data["founder_id"] = interaction.user.id
    party_data["completion_msg_ids"] = []
    party_data["is_completed"] = False
    party_data["msg_id"] = None
    party_data["notif_msg_id"] = None

    if old_msg_id:
        try:
            old_msg = await channel.fetch_message(old_msg_id)
            await old_msg.delete()
        except Exception:
            pass

    if old_notif_id:
        try:
            old_notif = await channel.fetch_message(old_notif_id)
            await old_notif.delete()
        except Exception:
            pass

    for msg_id in old_completion_ids:
        try:
            old_completion = await channel.fetch_message(msg_id)
            await old_completion.delete()
        except Exception:
            pass

    notif_embed = discord.Embed(
        title="🎉 Skládá se nová parta",
        description=f"do lokace **{lokace}**\n\nZakladatel: {interaction.user.mention}",
        color=0x00FF00,
    )
    notif_msg = await channel.send(content="@everyone", embed=notif_embed)
    party_data["notif_msg_id"] = notif_msg.id

    await create_initial_party_embed()

async def create_initial_party_embed():
    guild = bot.get_guild(SERVER_ID)
    channel = guild.get_channel(CHANNEL_ID) if guild else None

    if not channel or not party_data["lokace"]:
        return

    total = get_total_members()
    cas_display = f"<t:{party_data['cas_timestamp']}:f>"
    remaining_time = get_remaining_time()
    timer_display = format_timer(remaining_time)

    embed = discord.Embed(
        title="🎮 Party Maker",
        description=(
            f"**Lokace:** {party_data['lokace']}\n"
            f"**Zahájena:** {cas_display}\n\n"
            "Rovnoměrná dělba dropu dle CP pravidel\n\n"
            f"**Obsazení: {total}/9**\n"
            f"\n⏱️ **Countdown:** {timer_display}\n"
            f"*Po uplynutí doby bude sekvence převedena do spánkového režimu*"
        ),
        color=0x0099FF,
    )

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

    embed.add_field(name="✅ OBSAZENÉ ROLE", value="Žádné role zatím obsazeny", inline=False)

    remaining_roles = [f"{role} (0/{max_slot})" for role, max_slot in ROLE_SLOTS.items()]
    embed.add_field(name="📋 ZBÝVAJÍCÍ SLOTY", value="\n".join(remaining_roles), inline=False)
    embed.set_footer(text="Klikni na 'Nová parta' pro reset")

    msg = await channel.send(embed=embed, view=PartyView())
    party_data["msg_id"] = msg.id

async def update_party_embed():
    async with party_data["update_lock"]:
        guild = bot.get_guild(SERVER_ID)
        channel = guild.get_channel(CHANNEL_ID) if guild else None

        if not channel or not party_data["lokace"]:
            return

        total = get_total_members()
        cas_display = f"<t:{party_data['cas_timestamp']}:f>"
        remaining_time = get_remaining_time()
        timer_display = format_timer(remaining_time)

        embed = discord.Embed(
            title="🎮 Party Maker",
            description=(
                f"**Lokace:** {party_data['lokace']}\n"
                f"**Zahájena:** {cas_display}\n\n"
                "Rovnoměrná dělba dropu dle CP pravidel\n\n"
                f"**Obsazení: {total}/9**\n"
                f"\n⏱️ **Countdown:** {timer_display}\n"
                f"*Po uplynutí doby bude sekvence převedena do spánkového režimu*"
            ),
            color=0x0099FF,
        )

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

        embed.set_footer(text="Klikni na 'Nová parta' pro reset")

        if party_data["msg_id"]:
            try:
                msg = await channel.fetch_message(party_data["msg_id"])
                await msg.edit(embed=embed, view=PartyView())
            except discord.NotFound:
                msg = await channel.send(embed=embed, view=PartyView())
                party_data["msg_id"] = msg.id

        if total == 9 and not party_data["is_completed"]:
            if not missing_required:
                party_data["is_completed"] = True

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

                party_data["timer_start"] = int(datetime.now().timestamp())
                party_data["timer_duration"] = 15 * 60
                party_data["last_embed_update"] = 0
            else:
                party_data["is_completed"] = True

                missing_text = ", ".join(missing_required)
                warning_embed = discord.Embed(
                    title="⚠️ Party (9/9) ale chybí role!",
                    description=f"Parta je plná, ale chybí: {missing_text}\nNěkdo se musí odhlásit a nahradit jej!",
                    color=0xFF9900,
                )
                completion_msg = await channel.send(embed=warning_embed)
                party_data["completion_msg_ids"].append(completion_msg.id)

@tasks.loop(seconds=1)
async def timer_checker():
    try:
        if not party_data["is_idle"]:
            remaining = get_remaining_time()

            if remaining <= 0:
                print(f"⏱️ [BACKGROUND LOOP] TIMEOUT DETEKOVÁN! Spouštím reset...")
                await reset_to_idle_state()
            else:
                current_time = int(datetime.now().timestamp())
                if current_time != party_data["last_embed_update"]:
                    party_data["last_embed_update"] = current_time
                    await update_party_embed()
    except Exception as e:
        print(f"❌ [TIMER_CHECKER] Chyba: {e}")

@timer_checker.before_loop
async def before_timer_checker():
    await bot.wait_until_ready()
    print("✅ Timer checker background loop spuštěn!")

@bot.event
async def on_ready():
    print(f"✅ Bot {bot.user} je online!")
    await bot.tree.sync()
    if not timer_checker.is_running():
        timer_checker.start()

@bot.tree.command(name="farma", description="Spustit Party Maker")
async def farma_cmd(interaction: discord.Interaction):
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
    await bot.tree.sync()
    await ctx.send("✅ Slash commands resyncnuté.")

bot.run(os.getenv("DISCORD_TOKEN"))
