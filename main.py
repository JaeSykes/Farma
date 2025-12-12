import discord
from discord.ext import commands
from discord.ui import Select, View, Button
import os
from datetime import datetime

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Konfigurace
CHANNEL_ID = 1448991981765394432
SERVER_ID = 1397286059406000249

LOKACE = {
    '🐉 Dragon Valley': 'Dragon Valley',
    '🐲 Lair of Antharas': 'Lair of Antharas',
    '🕳️ Giant Cave': 'Giant Cave',
    '🌱 Seed of Annihilation': 'Seed of Annihilation',
    '🏚️ TOP Cata/Necro': 'TOP Cata/Necro',
    '⚒️ Forge of Gods': 'Forge of Gods',
}

ROLE_SLOTS = {
    'Damage Dealers': 4,
    'Swordsinger': 1,
    'Bladedance': 1,
    'Healer': 1,
    'Recharge': 1,
    'Buffer': 1,
    'Spoil': 1,
    'EXP': 1
}

# Globální proměnné
party_data = {
    'lokace': None,
    'cas': None,
    'sloty': {role: [] for role in ROLE_SLOTS},
    'msg_id': None,
    'notif_msg_id': None
}

class LokaceSelect(Select):
    def __init__(self):
        options = [discord.SelectOption(label=lokace, emoji=emoji) 
                  for emoji, lokace in LOKACE.items()]
        super().__init__(placeholder="Vyber lokaci pro farmu...", 
                        min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        lokace_vyber = self.values[0]
        await interaction.response.defer()
        await create_new_party(interaction, lokace_vyber)

class RoleSelect(Select):
    def __init__(self):
        options = [discord.SelectOption(label=role, emoji="✅") 
                  for role in ROLE_SLOTS]
        super().__init__(placeholder="Vyber si roli v partě...", 
                        min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        role = self.values[0]
        user = interaction.user
        
        # Ověř zda je slot volný
        if len(party_data['sloty'][role]) >= ROLE_SLOTS[role]:
            await interaction.response.send_message(
                f"❌ Role **{role}** je již obsazená!", 
                ephemeral=True
            )
            return
        
        # Ověř zda je uživatel už v jiné roli
        for r, members in party_data['sloty'].items():
            if user in members:
                members.remove(user)
        
        # Přidej uživatele
        party_data['sloty'][role].append(user)
        await interaction.response.send_message(
            f"✅ Přihlášen na roli **{role}**!", 
            ephemeral=True
        )
        await update_party_embed()

class PartyView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(RoleSelect())
    
    @discord.ui.button(label="Odhlásit se", style=discord.ButtonStyle.red, custom_id="btn_leave")
    async def leave_button(self, button: Button, interaction: discord.Interaction):
        user = interaction.user
        found = False
        
        for role, members in party_data['sloty'].items():
            if user in members:
                members.remove(user)
                found = True
                break
        
        if found:
            await interaction.response.send_message(
                f"✅ Odhlášen z party!", 
                ephemeral=True
            )
            await update_party_embed()
        else:
            await interaction.response.send_message(
                f"❌ Nejsi v partě!", 
                ephemeral=True
            )
    
    @discord.ui.button(label="Nová farma", style=discord.ButtonStyle.blurple, custom_id="btn_new_party")
    async def new_party_button(self, button: Button, interaction: discord.Interaction):
        await interaction.response.defer()
        
        # Smaž starou notifikaci
        channel = bot.get_channel(CHANNEL_ID)
        if party_data['notif_msg_id'] and channel:
            try:
                msg = await channel.fetch_message(party_data['notif_msg_id'])
                await msg.delete()
            except:
                pass
        
        # Reset dat
        party_data['sloty'] = {role: [] for role in ROLE_SLOTS}
        
        # Zobraz lokace select
        embed = discord.Embed(
            title="🌍 Vyber lokaci pro novou farmu",
            description="Kde chceš farmit?",
            color=0x0099ff
        )
        view = View()
        view.add_item(LokaceSelect())
        
        await interaction.followup.send(embed=embed, view=view, ephemeral=False)

async def create_new_party(interaction, lokace):
    channel = bot.get_channel(CHANNEL_ID)
    
    # Smaž starý embed
    if party_data['msg_id'] and channel:
        try:
            old_msg = await channel.fetch_message(party_data['msg_id'])
            await old_msg.delete()
        except:
            pass
    
    # Smaž starou notifikaci
    if party_data['notif_msg_id'] and channel:
        try:
            old_notif = await channel.fetch_message(party_data['notif_msg_id'])
            await old_notif.delete()
        except:
            pass
    
    # Reset party
    party_data['lokace'] = lokace
    party_data['cas'] = datetime.now().strftime("%d.%m.%Y %H:%M")
    party_data['sloty'] = {role: [] for role in ROLE_SLOTS}
    
    # Pošli notifikaci
    notif_embed = discord.Embed(
        title="🎉 Skládá se nová farm parta",
        description=f"do lokace **{lokace}**",
        color=0x00ff00
    )
    notif_msg = await channel.send(embed=notif_embed)
    party_data['notif_msg_id'] = notif_msg.id
    
    # Vytvoř party embed
    await update_party_embed()

async def update_party_embed():
    channel = bot.get_channel(CHANNEL_ID)
    if not channel or not party_data['lokace']:
        return
    
    # Počítej členy
    total = sum(len(members) for members in party_data['sloty'].values())
    
    # Vytvoř embed
    embed = discord.Embed(
        title="🎮 Společná party farma",
        description=f"**Lokace:** {party_data['lokace']}\n**Čas:** {party_data['cas']}\n**Zahájena:** {party_data['cas']}\n\n"
                   f"Rovnoměrná dělba dropu dle CP pravidel\n\n"
                   f"**Obsazení: {total}/9**",
        color=0x0099ff
    )
    
    # Přidej sloty
    for role, max_slot in ROLE_SLOTS.items():
        members = party_data['sloty'][role]
        member_text = ", ".join([m.mention for m in members]) if members else "❌ Volné"
        embed.add_field(
            name=f"{role} ({len(members)}/{max_slot})",
            value=member_text,
            inline=False
        )
    
    embed.set_footer(text="Klikni na Nová farma pro reset")
    
    # Vytvoř/aktualizuj zprávu
    if party_data['msg_id']:
        try:
            msg = await channel.fetch_message(party_data['msg_id'])
            await msg.edit(embed=embed)
        except:
            msg = await channel.send(embed=embed, view=PartyView())
            party_data['msg_id'] = msg.id
    else:
        msg = await channel.send(embed=embed, view=PartyView())
        party_data['msg_id'] = msg.id
    
    # Pokud je party plná, pošli notifikaci
    if total == 9:
        participants = " ".join([m.mention for members in party_data['sloty'].values() for m in members])
        full_embed = discord.Embed(
            title="✅ Parta složena!",
            description=f"Regroup u **Gatekeeper** před portem do **{party_data['lokace']}**\n\n"
                       f"Účastníci: {participants}",
            color=0x00ff00
        )
        await channel.send(embed=full_embed)

@bot.event
async def on_ready():
    print(f"✅ Bot {bot.user} je online!")

@bot.slash_command(name="farma", description="Spustit party finder pro farmu")
async def farma(ctx):
    # Zobraz lokace select
    embed = discord.Embed(
        title="🌍 Vyber lokaci pro farmu",
        description="Dostupné lokace:",
        color=0x0099ff
    )
    for emoji, lokace in LOKACE.items():
        embed.add_field(name=emoji, value=lokace, inline=True)
    
    view = View()
    view.add_item(LokaceSelect())
    
    await ctx.respond(embed=embed, view=view, ephemeral=False)

bot.run(os.getenv('DISCORD_TOKEN'))
