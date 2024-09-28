from asyncio import tasks
from datetime import timedelta
import discord
import aiosqlite
import schedule
import asyncio
from discord.ext import commands
from discord import app_commands
import os
from dotenv import load_dotenv # type: ignore
from database import *
import datetime
from datetime import timedelta

#-------------------------------------------------------------------------------------------------------------------------

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

#-------------------------------------------------------------------------------------------------------------------------

activity = discord.Game(name="Creating Tournament for you <3")
bot = commands.Bot(command_prefix="!", intents=discord.Intents.all(), activity=activity, status=discord.Status.online)

#-------------------------------------------------------------------------------------------------------------------------

class RoleButton(discord.ui.View):
    def __init__(self, role_id: int):
        super().__init__(timeout=None)  # La vue ne va pas expirer
        self.role_id = role_id

    @discord.ui.button(label="Toggle Notifications", style=discord.ButtonStyle.secondary, emoji="<:RTLlogo:1281944370211328133>")
    async def toggle_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        role = interaction.guild.get_role(self.role_id)

        if role is None:
            await interaction.response.send_message("Role not found!", ephemeral=True)
            return

        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(f"You won't get notifications for tournaments.", ephemeral=True)
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"You will now get notifications for tournaments", ephemeral=True)

#-------------------------------------------------------------------------------------------------------------------------

@bot.event
async def on_ready():
    # Connexion à la base de données
    bot.db = await aiosqlite.connect('Main.db')

    # Création de la table si elle n'existe pas
    await create_table()

    print("Bot is online ! ", "| Name :", bot.user.name, "| ID :", bot.user.id)
    print("//////////////////////////////////")
    try:
        synced = await bot.tree.sync()
        synced_names = [command.name for command in synced]  # Récupère les noms des commandes synchronisées
        print(f"{len(synced)} commandes ont été synchronisées : {', '.join(synced_names)}")
    except Exception as e:
        print(e)

    guild = bot.get_guild(1281946620161949779)  # Remplace GUILD_ID par l'ID de ton serveur
    channel = guild.get_channel(1282064125496660038)  # Remplace CHANNEL_ID par l'ID du canal où tu veux envoyer le message
    
    role_id = 1282064508621160488  # Remplace par l'ID du rôle de notification
    view = RoleButton(role_id)
    
    # Vérifie si un message existe déjà avec ce bouton dans le canal (facultatif)
    async for message in channel.history(limit=10):  # On vérifie les 10 derniers messages
        if message.author == bot.user and message.embeds:  # Si le bot a déjà envoyé un message avec un embed
            await message.edit(embed=message.embeds[0], view=view)  # Met à jour la vue avec le bouton
            break
    else:
        # Si aucun message n'a été trouvé, on envoie un nouveau message avec l'embed et le bouton
        embed = discord.Embed(
            title="Tournaments Notifications",
            description="Click the button below to toggle the notifications.",
            color=discord.Color(int("433D8B", 16))
        )
        embed.set_footer(text="Powered By Rocket Tournament League", icon_url="https://i.imgur.com/mfngNMH.png")
        await channel.send(embed=embed, view=view)

    run_scheduler()
    while True:
        schedule.run_pending()
        await asyncio.sleep(1)

    

#-------------------------------------------------------------------------------------------------------------------------

@bot.event
async def on_member_join(member):
    # Récupérer le serveur (guild) où le membre a rejoint
    guild = member.guild
    
    # Récupérer le rôle que vous souhaitez attribuer au membre
    role = discord.utils.get(guild.roles, id=1281953212529901601)

    # Vérifier si le rôle existe et si le membre n'a pas déjà ce rôle
    if role is not None and role not in member.roles:
        # Ajouter le rôle au membre
        await member.add_roles(role)

    insert_data(member.id, member.display_name)

#-------------------------------------------------------------------------------------------------------------------------


async def scheduled_weekly():
    await create_tournament_channels()
    await post_weekly()

def run_scheduler():
    schedule.every().sunday.at("12:00").do(lambda: asyncio.run_coroutine_threadsafe(scheduled_weekly(), bot.loop))
    schedule.every().sunday.at("11:50").do(lambda: asyncio.run_coroutine_threadsafe(cleanup_old_tournaments(), bot.loop))
    


#-------------------------------------------------------------------------------------------------------------------------

class RegistrationButton(discord.ui.View):
    def __init__(self, participants, channel_id):
        super().__init__(timeout=None)  # View will not expire
        self.participants = participants
        self.channel_id = channel_id

    @discord.ui.button(label="Join/Leave Tournament", style=discord.ButtonStyle.secondary)
    async def toggle_registration(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user

        # Vérifier si l'utilisateur est déjà inscrit
        if user in self.participants:
            self.participants.remove(user)
            action = "removed"
        else:
            # Vérifier si la limite de 16 participants est atteinte
            if len(self.participants) >= 16:
                await interaction.response.send_message("The tournament is full! Only 16 participants are allowed.", ephemeral=True)
                return

            self.participants.append(user)
            action = "added"

        # Répondre à l'utilisateur
        await interaction.response.send_message(f"{user.mention}, you have been **{action}** from the participants list.", ephemeral=True)

        # Mettre à jour l'embed avec la liste des participants et ajouter le compteur
        participants_list = "\n".join([member.mention for member in self.participants]) or "No participants yet"
        participants_count = f"**Participants: {len(self.participants)}/16**\n\n{participants_list}"
        
        embed = discord.Embed(
            title="Tournament Participants",
            description=participants_count,
            color=discord.Color(int("433D8B", 16))
        )
        embed.set_footer(text="Powered By Rocket Tournament League", icon_url="https://i.imgur.com/mfngNMH.png")

        # Envoyer l'embed mis à jour
        channel = interaction.guild.get_channel(self.channel_id)
        
        # Rechercher le message avec l'embed précédent
        found = False
        async for message in channel.history(limit=10):
            if message.author == interaction.guild.me and message.embeds:
                await message.edit(embed=embed)
                found = True
                break
        
        if not found:
            await channel.send(embed=embed)




class TeamRegistrationButton(discord.ui.View):
    def __init__(self, teams, required_size, channel_id):
        super().__init__(timeout=None)
        self.teams = teams
        self.required_size = required_size
        self.channel_id = channel_id

    @discord.ui.button(label="Create/Join Team", style=discord.ButtonStyle.success)
    async def create_or_join_team(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        await interaction.response.send_message("Please enter your team name:", ephemeral=True)

        def check(m):
            return m.author == user and m.channel == interaction.channel

        team_name_message = await bot.wait_for('message', check=check)
        team_name = team_name_message.content

        # Vérifier si l'équipe existe déjà
        team = next((team for team in self.teams if team['name'] == team_name), None)
        if team:
            if len(team['members']) < self.required_size:
                captain = team['members'][0]
                embed_captain = discord.Embed(
                    title=f"{self.team['name']} Management",
                    description=f"{user.mention} wants to join your team **{team_name}**. Do you accept?",
                    color=discord.Color(int("433D8B", 16))
                )
                embed_captain.set_footer(text="Powered By Rocket Tournament League", icon_url="https://i.imgur.com/mfngNMH.png")
                embed_player = discord.Embed(
                    title="Tournament Notification",
                    description=f"Your request to join **{team_name}** has been sent to the captain.",
                    color=discord.Color(int("433D8B", 16))
                )
                embed_player.set_footer(text="Powered By Rocket Tournament League", icon_url="https://i.imgur.com/mfngNMH.png")
                await captain.send(embed=embed_captain, view=AcceptOrRejectView(user, team))
                await interaction.followup.send(embed=embed_player, ephemeral=True)
            else:
                embed_team_full = discord.Embed(
                    title="Team is Full",
                    description=f"Team **{team_name}** is already full.",
                    color=discord.Color(int("433D8B", 16))
                )
                embed_team_full.set_footer(text="Powered By Rocket Tournament League", icon_url="https://i.imgur.com/mfngNMH.png")
                await interaction.followup.send(embed=embed_team_full, ephemeral=True)
        else:
            # Vérifier si le nombre d'équipes a atteint la limite de 16
            if len(self.teams) >= 16:
                embed_tournament_full = discord.Embed(
                    title="Tournament is Full",
                    description="The maximum number of 16 teams has been reached. No new teams can be created.",
                    color=discord.Color(int("433D8B", 16))
                )
                embed_tournament_full.set_footer(text="Powered By Rocket Tournament League", icon_url="https://i.imgur.com/mfngNMH.png")
                await interaction.followup.send(embed=embed_tournament_full, ephemeral=True)
                return

            # Créer une nouvelle équipe
            self.teams.append({'name': team_name, 'members': [user]})
            embed_team_creation = discord.Embed(
                    title=f"{team_name} has been created !",
                    description=f"You have created and joined team **{team_name}** as the captain.",
                    color=discord.Color(int("433D8B", 16))
                )
            embed_team_creation.set_footer(text="Powered By Rocket Tournament League", icon_url="https://i.imgur.com/mfngNMH.png")
            await interaction.followup.send(embed=embed_team_creation, ephemeral=True)
            embed_new_captain = discord.Embed(
                    title=f"Hi captain !",
                    description=f"You are now the captain of the team **{team_name}**. You will receive requests from players who want to join.",
                    color=discord.Color(int("433D8B", 16))
                )
            embed_new_captain.set_footer(text="Powered By Rocket Tournament League", icon_url="https://i.imgur.com/mfngNMH.png")
            await user.send(embed=embed_new_captain)
            await self.update_team_list(interaction)


    @discord.ui.button(label="Leave Team", style=discord.ButtonStyle.danger)
    async def leave_team(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        team = next((team for team in self.teams if user in team['members']), None)

        if team:
            team['members'].remove(user)
            if not team['members']:  # Supprimer l'équipe si elle est vide
                self.teams.remove(team)
            await interaction.response.send_message(f"You have left the team **{team['name']}**.", ephemeral=True)
        else:
            await interaction.response.send_message("You are not part of any team.", ephemeral=True)

        await self.update_team_list(interaction)

    async def update_team_list(self, interaction):
        # Compteur des équipes
        teams_list = "\n".join([f"**{team['name']}**: {', '.join([member.mention for member in team['members']])}" for team in self.teams]) or "No teams yet"
        teams_count = f"**Teams: {len(self.teams)}/16**\n\n{teams_list}"
        
        embed = discord.Embed(
            title="Tournament Teams",
            description=teams_count,
            color=discord.Color(int("433D8B", 16))
        )
        embed.set_footer(text="Powered By Rocket Tournament League", icon_url="https://i.imgur.com/mfngNMH.png")

        channel = interaction.guild.get_channel(self.channel_id)
        async for message in channel.history(limit=10):
            if message.author == interaction.guild.me and message.embeds:
                await message.edit(embed=embed)
                break
        else:
            await channel.send(embed=embed)


# Classe pour gérer l'acceptation ou le rejet des demandes de rejoindre une équipe
class AcceptOrRejectView(discord.ui.View):
    def __init__(self, player, team):
        super().__init__(timeout=60)  # Délai de 60 secondes pour répondre
        self.player = player
        self.team = team

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.team['members'].append(self.player)
        embed_captain = discord.Embed(
            title=f"{self.team['name']} Management",
            description=f"{self.player.mention} has been accepted into the team.",
            color=discord.Color(int("433D8B", 16))
        )
        embed_captain.set_footer(text="Powered By Rocket Tournament League", icon_url="https://i.imgur.com/mfngNMH.png")
        embed_player = discord.Embed(
            title="Tournament Notification",
            description=f"You have been accepted into the team **{self.team['name']}**!",
            color=discord.Color(int("433D8B", 16))
        )
        embed_player.set_footer(text="Powered By Rocket Tournament League", icon_url="https://i.imgur.com/mfngNMH.png")
        await interaction.message.edit(embed=embed_captain)
        await self.player.send(embed=embed_player)
        await self.update_team_list(interaction)


    @discord.ui.button(label="Reject", style=discord.ButtonStyle.danger)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed_captain = discord.Embed(
            title=f"{self.team['name']} Management",
            description=f"{self.player.mention} has been rejected from the team.",
            color=discord.Color(int("433D8B", 16))
        )
        embed_captain.set_footer(text="Powered By Rocket Tournament League", icon_url="https://i.imgur.com/mfngNMH.png")
        embed_player = discord.Embed(
            title="Tournament Notification",
            description=f"Your request to join **{self.team['name']}** has been rejected.",
            color=discord.Color(int("433D8B", 16))
        )
        embed_player.set_footer(text="Powered By Rocket Tournament League", icon_url="https://i.imgur.com/mfngNMH.png")
        await interaction.message.edit(embed=embed_captain)
        await self.player.send(embed=embed_player)

#-------------------------------------------------------------------------------------------------------------------------

async def create_tournament_channels():
    guild = bot.get_guild(1281946620161949779)
    channel = bot.get_channel(1282064244044595200)

    tournaments = [
        ("Monday", "18PM", "1v1"),
        ("Monday", "21PM", "2v2"),
        ("Tuesday", "18PM", "2v2"),
        ("Tuesday", "21PM", "3v3"),
        ("Wednesday", "18PM", "3v3"),
        ("Wednesday", "21PM", "1v1"),
        ("Thursday", "18PM", "1v1"),
        ("Thursday", "21PM", "2v2"),
        ("Friday", "18PM", "2v2"),
        ("Friday", "21PM", "3v3"),
        ("Saturday", "18PM", "3v3"),
        ("Saturday", "21PM", "1v1")
    ]

    for day, time, gamemode in tournaments:
        category_name = f"{day} - {time} - {gamemode}"
        
        # Créer la catégorie
        category = await guild.create_category(category_name)

        # Créer le salon texte "registration" dans la catégorie
        registration_channel = await guild.create_text_channel('registration', category=category)

        # Créer un embed d'information sur le tournoi
        tournament_embed = discord.Embed(
            title=f"Registration for {gamemode} Tournament",
            description=f"This is the registration for the {gamemode} tournament happening on {day} at {time}.",
            color=discord.Color(int("433D8B", 16))
        )

        if gamemode == "1v1":
            participants = []
            view = RegistrationButton(participants, registration_channel.id)
        else:
            required_size = 2 if gamemode == "2v2" else 3
            teams = []  # Liste des équipes
            view = TeamRegistrationButton(teams, required_size, registration_channel.id)

        # Envoyer un embed avec les informations du tournoi
        tournament_embed = discord.Embed(
            title=f"Registration for {gamemode} Tournament",
            description=f"This is the registration for the {gamemode} tournament happening on {day} at {time}.",
            color=discord.Color(int("433D8B", 16))
        )
        
        await registration_channel.send(embed=tournament_embed, view=view)

        # Créer un embed pour la liste des participants ou équipes
        if gamemode == "1v1":
            participants_embed = discord.Embed(
                title="Tournament Participants",
                description="No participants yet",
                color=discord.Color(int("433D8B", 16))
            )
        else:
            participants_embed = discord.Embed(
                title="Tournament Teams",
                description="No teams yet",
                color=discord.Color(int("433D8B", 16))
            )

        participants_embed.set_footer(text="Powered By Rocket Tournament League", icon_url="https://i.imgur.com/mfngNMH.png")

        # Envoyer l'embed de la liste des participants ou équipes
        await registration_channel.send(embed=participants_embed)


async def post_weekly():
    channel = bot.get_channel(1282064244044595200)
    role = discord.utils.get(channel.guild.roles, id=1282064508621160488)

    # Liste des tournois avec jour, heure et format
    tournaments = [
        ("Monday", "18PM", "1v1"),
        ("Monday", "21PM", "2v2"),
        ("Tuesday", "18PM", "2v2"),
        ("Tuesday", "21PM", "3v3"),
        ("Wednesday", "18PM", "3v3"),
        ("Wednesday", "21PM", "1v1"),
        ("Thursday", "18PM", "1v1"),
        ("Thursday", "21PM", "2v2"),
        ("Friday", "18PM", "2v2"),
        ("Friday", "21PM", "3v3"),
        ("Saturday", "18PM", "3v3"),
        ("Saturday", "21PM", "1v1")
    ]

    # Créer le planning des tournois avec des liens vers les salons
    description = ""
    for day, time, gamemode in tournaments:
        category_name = f"{day} - {time} - {gamemode}"
        category = discord.utils.get(channel.guild.categories, name=category_name)
        if category:
            registration_channel = discord.utils.get(category.channels, name="registration")
            if registration_channel:
                description += f"**{day} {time} {gamemode}**: [Join Here]({registration_channel.jump_url})\n"

    # Ajouter un jour sans tournoi
    description += "\n**Sunday**: Break Day"

    # Embed pour le planning
    embed = discord.Embed(
        title="Rocket League Tournaments - Weekly Schedule",
        description=description,
        color=discord.Color(int("433D8B", 16))
    )
    embed.timestamp = discord.utils.utcnow()
    embed.set_footer(text="Powered By Rocket Tournament League", icon_url="https://i.imgur.com/mfngNMH.png")

    # Envoi de l'embed avec le planning
    await channel.send(content=f"{role.mention}", embed=embed)


#-------------------------------------------------------------------------------------------------------------------------


async def cleanup_old_tournaments():
    guild = bot.get_guild(1281946620161949779)
    categories = [category for category in guild.categories if category.name.endswith('- 1v1') or category.name.endswith('- 2v2') or category.name.endswith('- 3v3')]
    
    for category in categories:
        # Supprimer tous les salons dans la catégorie
        for channel in category.channels:
            await channel.delete()

        # Supprimer la catégorie
        await category.delete()

#-------------------------------------------------------------------------------------------------------------------------

@bot.tree.command(name="stats", description="Display your statistics.")
async def aitaneuh(interaction: discord.Interaction):
    member = interaction.user
    user_data = await get_data(str(member.id))  # Récupérer les stats de la base de données

    if user_data:
        discord_id, discord_username, tournament_number, tournament_wins, match_number, match_wins = user_data
        embed = discord.Embed(
            title=f"{member.display_name}'s Statistics", 
            color=discord.Color(int("433D8B", 16))
        )
        embed.add_field(name="Tournaments played", value=tournament_number, inline=False)
        embed.add_field(name="Tournaments won", value=tournament_wins, inline=False)
        embed.add_field(name="Matchs played", value=match_number, inline=False)
        embed.add_field(name="Matchs won", value=match_wins, inline=False)
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message(f"{member.mention}, you haven't done any tournaments until now.", ephemeral=True)

#-------------------------------------------------------------------------------------------------------------------------


# Fonction pour mettre à jour les stats après une victoire
async def add_tournament_win(user_id):
    async with aiosqlite.connect('Main.db') as db:
        await db.execute("""
            UPDATE users 
            SET tournament_number = tournament_number + 1, tournament_wins = tournament_wins + 1 
            WHERE discord_id = ?
        """, (user_id,))
        await db.commit()

# Fonction pour mettre à jour les stats après une défaite
async def add_tournament_loss(user_id):
    async with aiosqlite.connect('Main.db') as db:
        await db.execute("""
            UPDATE users 
            SET tournament_number = tournament_number + 1
            WHERE discord_id = ?
        """, (user_id,))
        await db.commit()

#-------------------------------------------------------------------------------------------------------------------------

# Fonction pour mettre à jour les stats après une victoire
async def add_match_win(user_id):
    async with aiosqlite.connect('Main.db') as db:
        await db.execute("""
            UPDATE users 
            SET match_number = match_number + 1, match_wins = match_wins + 1 
            WHERE discord_id = ?
        """, (user_id,))
        await db.commit()

# Fonction pour mettre à jour les stats après une défaite
async def add_match_loss(user_id):
    async with aiosqlite.connect('Main.db') as db:
        await db.execute("""
            UPDATE users 
            SET match_number = match_number + 1
            WHERE discord_id = ?
        """, (user_id,))
        await db.commit()


#-------------------------------------------------------------------------------------------------------------------------




#-------------------------------------------------------------------------------------------------------------------------



class AitaneuhButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # View will not expire

        self.add_item(discord.ui.Button(label="Follow him on Twitter", style=discord.ButtonStyle.link, emoji="<:Aitaneuh:1281945073973723247>", url="https://x.com/aitaneuh"))

@bot.tree.command(name="aitaneuh", description="Who is Aitaneuh ?")
@commands.has_permissions(administrator=True)
async def aitaneuh(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Who is Aitaneuh?",
        description="Aitaneuh is the creator of Rocket Tournament League <:RTLlogo:1281944370211328133>. He did the Discord server and coded the Bot by himself. Sadly, he is better in programming than in Rocket League.",
        color=discord.Color(int("433D8B", 16))
    )
    embed.set_footer(text="Powered By Rocket Tournament League", icon_url="https://i.imgur.com/mfngNMH.png") 

    view = AitaneuhButton()

    await interaction.response.send_message(embed=embed, view=view)

class RoleButton(discord.ui.View):
    def __init__(self, role_id: int):
        super().__init__(timeout=None)  # View will not expire
        self.role_id = role_id

    @discord.ui.button(label="Toggle Notifications", style=discord.ButtonStyle.secondary, emoji="<:RTLlogo:1281944370211328133>")
    async def toggle_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        role = interaction.guild.get_role(self.role_id)

        if role is None:
            await interaction.response.send_message("Role not found!", ephemeral=True)
            return

        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(f"You won't get notifications for tournaments.", ephemeral=True)
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"You will now get notifications for tournaments", ephemeral=True)

@bot.tree.command(name="admin_notification_button_send", description="send the notification message")
@commands.has_permissions(administrator=True)
async def admin_notification_button_send(interaction: discord.Interaction):
    if interaction.user.guild_permissions.administrator:
        embed = discord.Embed(
            title="Tournaments Notifications",
            description="Click the button below to toggle the notifications.",
            color=discord.Color(int("433D8B", 16))
        )
        embed.set_footer(text="Powered By Rocket Tournament League", icon_url="https://i.imgur.com/mfngNMH.png")
        
        role_id = 1282064508621160488

        view = RoleButton(role_id)
        await interaction.channel.send(embed=embed, view=view)
    else:
        await interaction.response.send_message(f"{interaction.user.mention}, you aren't an administrator.", ephemeral=True)

#-------------------------------------------------------------------------------------------------------------------------


@bot.tree.command(name="admin_clear", description="clear a channel")
@commands.has_permissions(administrator=True)
async def admin_clear(interaction: discord.Interaction):
    if interaction.user.guild_permissions.administrator:
        channel = interaction.channel
        await channel.purge()
    else:
        await interaction.response.send_message(f"{interaction.user.mention}, you aren't an administrator.", ephemeral=True)

#-------------------------------------------------------------------------------------------------------------------------

@bot.tree.command(name="admin_scheduled_weekly", description="scheduled weekly")
@commands.has_permissions(administrator=True)
async def admin_clear(interaction: discord.Interaction):
    if interaction.user.guild_permissions.administrator:
        await scheduled_weekly()
    else:
        await interaction.response.send_message(f"{interaction.user.mention}, you aren't an administrator.", ephemeral=True)

#-------------------------------------------------------------------------------------------------------------------------

@bot.tree.command(name="admin_cleanup_old_tournaments", description="cleanup old tournaments")
@commands.has_permissions(administrator=True)
async def admin_clear(interaction: discord.Interaction):
    if interaction.user.guild_permissions.administrator:
        await cleanup_old_tournaments()
    else:
        await interaction.response.send_message(f"{interaction.user.mention}, you aren't an administrator.", ephemeral=True)

#-------------------------------------------------------------------------------------------------------------------------

# initialition du token
bot.run(TOKEN)