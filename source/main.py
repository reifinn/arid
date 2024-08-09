# This is probably the shittiest piece of code youve ever seen. I didnt intend to make it open src so deal with lmao lalalala

import os
import json
import argparse
import discord
import asyncio
import unicodedata
import datetime
import time
import re
from discord.ext import commands, tasks
from discord.ext.commands import Greedy, Context
from typing import Literal, Optional
from discord import app_commands
from itertools import cycle
from urllib3 import Retry
from googleapiclient import discovery

# Sensitive INFO

TOKEN = "" # Bot Token
API_KEY = "" # Perspective API Key (Needed in order to run AI-Moderation)

# DISCORD BOT SETTINGS

intents = discord.Intents.all()
bot = commands.Bot(command_prefix='||', intents=intents)

# PERSPECTIVE API & MODERATION

toxicity_threshold = 0.85 # Change to any number.
defaultthreshold = 0.85

MODERATOR_ROLE_ID = [] # Read the name.
TRIAL_MODERATOR_ROLE_ID = [] # Read the name.
OWNER_ID = [] # Read the name.
MESSAGES = {} # Read the name.
SPAM_MESSAGES = {} # Read the name.

realll = discovery.build(
    "commentanalyzer",
    "v1alpha1",
    developerKey=API_KEY,
    discoveryServiceUrl="https://commentanalyzer.googleapis.com/$discovery/rest?version=v1alpha1",
    static_discovery=False,
)

strictusers = {
    # Users who have different moderation styles, if user is under heavy surveillance threshold will be increased:
    # How to use: 'UserId': 0.5 (Threshold)
}

optedout_users = [
    # For users who opt out.
    # How to ues: 'UserId'
]

# LIMITS & COOLDOWNS & STATS

WARNING_LIMITS = [3, 6, 9]
TIMEOUT_DURATION = 600
FAKE_WARNINGS = 0

# ROBOT STATUS

client_statuses = cycle(["Arid Desolation", "You", "Version 1.3B", f"Toxicity Threshold: {toxicity_threshold}%"])

url_regex = re.compile(
    r'http[s]?://'
    r'(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
)

# MAIN EVENT LISTENERS
@tasks.loop(seconds=10)
async def change_status():
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.watching, name=next(client_statuses)))

@bot.event
async def on_ready():
    await bot.tree.sync(guild=discord.Object(id=1245442301459959828))
    print(f'Logged in as {bot.user}')
    print('Bot is ready')
    change_status.start()


def is_mod_or_owner(user):
    return any(discord.utils.get(user.guild.roles, id=role_id) in user.roles for role_id in MODERATOR_ROLE_ID) or user.id in OWNER_ID

def log_message(message):
    log_path = 'logs.json'
    message_data = {
        'User ID:': str(message.author.id),
        'Username:': message.author.name,
        'messages': []
    }

    if os.path.exists(log_path):
        with open(log_path, 'r') as file:
            logs = json.load(file)
    else:
        logs = []

    if message_data['User ID:'] in optedout_users:
        return

    user_found = False
    for log in logs:
        if log['User ID:'] == message_data['User ID:']:
            user_found = True
            log['messages'].append({
                'Message:': message.content,
                'Time:': str(message.created_at)
            })
            break

    if not user_found:
        message_data['messages'].append({
            'Message:': message.content,
            'Time:': str(message.created_at)
        })
        logs.append(message_data)

    with open(log_path, 'w') as file:
        json.dump(logs, file, indent=4)


async def get_toxicity(text):
    analyze_request = {
        'comment': { 'text': text },
        'languages': ['en', 'es', 'fr', 'ru', 'zh', 'ja', 'de'],
        'requestedAttributes': {
            'TOXICITY': {},
            'INSULT': {},
            'THREAT': {}
        }
    }
    
    supported_attributes = ['TOXICITY', 'INSULT', 'THREAT']
    supported_languages = ['en', 'es', 'fr', 'ru', 'zh', 'ja', 'de']
    
    try:
        response = realll.comments().analyze(body=analyze_request).execute()
        
        attribute_scores = {}
        for attribute in supported_attributes:
            if attribute in response['attributeScores']:
                attribute_scores[attribute.lower()] = response['attributeScores'][attribute]['summaryScore']['value']
            else:
                attribute_scores[attribute.lower()] = None
        
        print(f"User Said: {text}")
        print(f"Toxicity: {attribute_scores['toxicity']}, Insulting: {attribute_scores['insult']}, Threatening: {attribute_scores['threat']}")
        
        return attribute_scores
    
    except Exception as e:
        print(f"Error analyzing text: {e}")
        return None

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    toxicity_scores = await get_toxicity(message.content)

    log_message(message)

    if is_mod_or_owner(message.author):
        return

    if str(message.author.id) in strictusers:
        toxicity_threshold = strictusers[str(message.author.id)]
    else:
        toxicity_threshold = defaultthreshold

    if toxicity_scores:
        toxicity_score = toxicity_scores.get('toxicity', 0)
        insult_score = toxicity_scores.get('insult', 0)
        threat_score = toxicity_scores.get('threat', 0)

        if toxicity_score > toxicity_threshold:
            user_id = str(message.author.id)
            user = message.author

            warnings = load_warnings()

            if user_id in warnings:
                warnings[user_id] += 1
            else:
                warnings[user_id] = 1

            save_warnings(warnings)

            channel_id = 1
            logging_channel = bot.get_channel(channel_id)

            embed = discord.Embed(title="Toxic Message Detected", color=0xff0000)
            embed.add_field(name="User", value=f"{message.author.name} ({message.author.id})", inline=False)
            embed.add_field(name="Message", value=message.content, inline=False)
            embed.add_field(name="Toxicity Score", value=toxicity_score, inline=False)
            embed.add_field(name="Insult Score", value=insult_score, inline=False)
            embed.add_field(name="Threat Score", value=threat_score, inline=False)
            embed.add_field(name="Warnings", value=warnings[user_id], inline=False)

            msg = await logging_channel.send(embed=embed)
            await msg.add_reaction('✅')
            await msg.add_reaction('❌')

            reply_message = await message.reply(
                f"{message.author.mention}, Please be civil and respectful! Warning count: {warnings[user_id]}"
            )

            await message.delete()

            guild = message.guild
            role_id_1 = 1
            role_id_2 = 1
            role_id_3 = 1

            if warnings[user_id] == 1:
                role_1 = guild.get_role(role_id_1)
                if role_1:
                    await user.add_roles(role_1, reason="First warning received")

            elif warnings[user_id] == 2:
                role_1 = guild.get_role(role_id_1)
                role_2 = guild.get_role(role_id_2)
                if role_1 and role_2:
                    await user.add_roles(role_1, role_2, reason="Second warning received")

            if warnings[user_id] in [3, 6, 9]:
                if warnings[user_id] == 3:
                    role_1 = guild.get_role(role_id_1)
                    role_2 = guild.get_role(role_id_2)
                    role_3 = guild.get_role(role_id_3)
                    await message.author.timeout(
                        datetime.timedelta(minutes=10),
                        reason="Reached 3 warnings"
                    )
                    await user.send(
                        f"{message.author.mention}, you have been timed out for reaching 3 warnings."
                    )
                    if role_1 and role_2 and role_3:
                        await user.add_roles(role_1, role_2, role_3, reason="Third warning received")
                elif warnings[user_id] == 6:
                    await message.author.timeout(
                        datetime.timedelta(minutes=20),
                        reason="Reached 6 warnings"
                    )
                    await user.send(
                        f"{message.author.mention}, you have been timed out again for reaching 6 warnings."
                    )
                elif warnings[user_id] == 9:
                    await message.author.kick(reason="Reached 9 warnings")
                    await user.send(
                        f"{message.author.mention}, you have been kicked for reaching 9 warnings."
                    )

            await asyncio.sleep(3)
            await reply_message.delete()

    if url_regex.search(message.content):
        whitelisted_channels = [] # Channel IDs
        if message.channel.id not in whitelisted_channels:
            user_id = str(message.author.id)
            user = message.author

            whitelisted_urls = [
                "https://google.com/",
                "https://roblox.com",
                "https://medal.tv",
                "https://cdn.discordapp.com",
                "https://media.discordapp.net",
                "https://tenor.com/",
                "https://discord.com/channels/"
            ]

            contains_whitelisted_url = any(url in message.content for url in whitelisted_urls)

            if not contains_whitelisted_url:
                warnings = load_warnings()

                if user_id in warnings:
                    warnings[user_id] += 1
                else:
                    warnings[user_id] = 1

                save_warnings(warnings)

                channel_id = 1
                logging_channel = bot.get_channel(channel_id)

                embed = discord.Embed(title="Link Detected", color=0xff0000)
                embed.add_field(name="User", value=f"{message.author.name} ({message.author.id})", inline=False)
                embed.add_field(name="Message", value=message.content, inline=False)
                embed.add_field(name="Warnings", value=warnings[user_id], inline=False)

                msg = await logging_channel.send(embed=embed)
                await msg.add_reaction('✅')
                await msg.add_reaction('❌')

                reply_message = await message.reply(
                    f"{message.author.mention}, Links are not allowed! Warning count: {warnings[user_id]}"
                )

                await message.delete()

                guild = message.guild
                role_id_1 = 1
                role_id_2 = 1
                role_id_3 = 1

                if warnings[user_id] == 1:
                    role_1 = guild.get_role(role_id_1)
                    if role_1:
                        await user.add_roles(role_1, reason="First warning received")

                elif warnings[user_id] == 2:
                    role_1 = guild.get_role(role_id_1)
                    role_2 = guild.get_role(role_id_2)
                    if role_1 and role_2:
                        await user.add_roles(role_1, role_2, reason="Second warning received")

                if warnings[user_id] in [3, 6, 9]:
                    if warnings[user_id] == 3:
                        role_1 = guild.get_role(role_id_1)
                        role_2 = guild.get_role(role_id_2)
                        role_3 = guild.get_role(role_id_3)
                        await message.author.timeout(
                            datetime.timedelta(minutes=10),
                            reason="Reached 3 warnings"
                        )
                        await user.send(
                            f"{message.author.mention}, you have been timed out for reaching 3 warnings."
                        )
                        if role_1 and role_2 and role_3:
                            await user.add_roles(role_1, role_2, role_3, reason="Third warning received")
                    elif warnings[user_id] == 6:
                        await message.author.timeout(
                            datetime.timedelta(minutes=20),
                            reason="Reached 6 warnings"
                        )
                        await user.send(
                            f"{message.author.mention}, you have been timed out again for reaching 6 warnings."
                        )
                    elif warnings[user_id] == 9:
                        await message.author.kick(reason="Reached 9 warnings")
                        await user.send(
                            f"{message.author.mention}, you have been kicked for reaching 9 warnings."
                        )

                await asyncio.sleep(3)
                await reply_message.delete()

    await bot.process_commands(message)


@bot.event
async def on_reaction_add(reaction, user):
    if user == bot.user:
        return

    if reaction.emoji == '❌' and reaction.message.channel.id == 1254376984121839639:
        if reaction.count >= 2:
            guild = reaction.message.guild
            user_id = int(reaction.message.embeds[0].fields[0].value.split(' ')[1].strip('()'))
            user = guild.get_member(user_id)
            warnings = load_warnings()
            if user is not None:
                if user.is_timed_out():
                    await user.remove_timeout()
                    warnings[user_id] -= 1
            print("Reached 2 Reactions")
            pass

@bot.event
async def on_member_join(member):
    role_id = 1248724281135992872
    role = discord.utils.get(member.guild.roles, id=role_id)
    await member.add_roles(role)

@bot.event
async def on_message_delete(message): # Delete Message Logs
    chanel = bot.get_channel(1)

    embed = discord.Embed(title="Message Deleted", color=0xff0000)
    embed.add_field(name="User: ", value=f"{message.author.name} ({message.author.id})", inline=False)
    embed.add_field(name="Channel: ", value=message.channel.mention, inline=False)
    embed.add_field(name="Message: ", value=message.content, inline=False)

    await chanel.send(embed=embed)

@bot.tree.command(name="roleall", description="Roles all users with a specific role.")
async def roleall(interaction: discord.Interaction, role: discord.Role):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return

    if not interaction.guild.me.guild_permissions.manage_roles:
        await interaction.response.send_message("I do not have permission to manage roles.", ephemeral=True)
        return

    for user in interaction.guild.members:
        if role not in user.roles:
            try:
                await user.add_roles(role)
            except discord.Forbidden:
                await interaction.response.send_message(f"Could not add role to {user.display_name}.", ephemeral=True)

    embed = discord.Embed(title="Role All", color=0xff0000)
    embed.add_field(name="Role Added", value=f"{role.mention} has been added to all users.", inline=False)
    await interaction.response.send_message(embed=embed)



@bot.tree.command(name="kick", description="Kicks a user.")
@app_commands.checks.has_any_role(*MODERATOR_ROLE_ID, "You don't have access to this command.")
async def kick(interaction: discord.Interaction, user: discord.Member, *, reason: Optional[str] = "No reason provided."):
    user_id = str(user.id)
    await user.kick(reason=reason)
    await interaction.response.send_message(f"{user.mention} has been kicked for: {reason} by {interaction.user.mention}.")
    channelid = 1254376984121839639
    loggingchannel = bot.get_channel(channelid)
    warnings = load_warnings()
    embed = discord.Embed(title="Admin Logs | Kick", color=0xff0000)
    embed.add_field(name="User: ", value=f"{user.name} ({user.id})", inline=False)
    embed.add_field(name="Moderator: ", value=f"{interaction.user.name} ({interaction.user.id})", inline=False)
    embed.add_field(name="Warnings: ", value=warnings[user_id], inline=False)
    await loggingchannel.send(embed=embed)

    await asyncio.sleep(3)
    await interaction.delete_original_response()

@bot.tree.command(name="ban", description="Bans a user.")
@app_commands.checks.has_any_role(*MODERATOR_ROLE_ID, "You don't have access to this command.")
async def ban(interaction: discord.Interaction, user: discord.Member, *, reason: Optional[str] = "No reason provided."):
    user_id = str(user.id)
    await user.ban(reason=reason)
    await interaction.response.send_message(f"{user.mention} has been banned for: {reason} by {interaction.user.mention}.")
    channelid = 1254376984121839639
    loggingchannel = bot.get_channel(channelid)
    warnings = load_warnings()
    embed = discord.Embed(title="Admin Logs | Ban", color=0xff0000)
    embed.add_field(name="User: ", value=f"{user.name} ({user.id})", inline=False)
    embed.add_field(name="Moderator: ", value=f"{interaction.user.name} ({interaction.user.id})", inline=False)
    embed.add_field(name="Warnings: ", value=warnings[user_id], inline=False)
    await loggingchannel.send(embed=embed)

    await asyncio.sleep(3)
    await interaction.delete_original_response()

@bot.tree.command(name="debug", description="A command for cool people only.")
@app_commands.checks.has_any_role(*MODERATOR_ROLE_ID, "You don't have access to this command.")
async def debug(interaction: discord.Interaction):
    await interaction.response.send_message("Debugged.")

    
roletoadd = 1
roletoremove = 1

@bot.tree.command(name="replaceallroles", description="A moderator only command to replace all roles.")
@app_commands.checks.has_any_role(*MODERATOR_ROLE_ID, "You don't have access to this command.")
async def replace_all_roles(interaction: discord.Interaction):
    if interaction.user.id not in MODERATOR_ROLE_ID:
        print("Bro")
        return
    
    guild = interaction.guild
    role_to_remove = guild.get_role(roletoremove)
    role_to_add = guild.get_role(roletoadd)
    
    if not role_to_remove or not role_to_add:
        await interaction.response.send_message("lmao bro there is no roles like this")
        return
    
    for member in guild.members:
        if role_to_remove in member.roles and role_to_add in member.roles:
            await member.remove_roles(role_to_remove)
            print(f"Removed Roles for {member.display_name}")
                
    print("Finished")
    
@bot.tree.command(name="stats",
                  description="Shows the number of warnings you have.")
@app_commands.checks.has_any_role(*MODERATOR_ROLE_ID, *TRIAL_MODERATOR_ROLE_ID,
                                  "You don't have access to this command.")
async def stats(interaction: discord.Interaction, user: discord.Member):
    user_id = str(user.id)
    warnings = load_warnings()

    if user_id in warnings:
        await interaction.response.send_message(
            f"{user.mention}, has {warnings[user_id]} warnings.")
    else:
        await interaction.response.send_message(
            f"{user.mention}, has no warnings.")
        

        
        
@bot.tree.command(name="cool", description="Cool")
async def cool(interaction: discord.Interaction, user:discord.Member, reason: str, proof: str = None):
    await interaction.response.send_message(
        f"{user.mention} is officially cool."
    )

import discord
import asyncio

@bot.tree.command(name="warn", description="Warns a user.")
@app_commands.checks.has_any_role(*MODERATOR_ROLE_ID, *TRIAL_MODERATOR_ROLE_ID, "You don't have access to this command.")
async def warn(interaction: discord.Interaction, user: discord.Member, reason: str, proof: discord.Attachment = None):
    user_id = str(user.id)
    warnings = load_warnings()

    if user_id in warnings:
        warnings[user_id] += 1
    else:
        warnings[user_id] = 1

    save_warnings(warnings)

    proof_message = f"\nProof: {proof.url}" if proof else ""
    await interaction.response.send_message(
        f"{user.mention} has been warned for {reason}. Current warnings: {warnings[user_id]}{proof_message}"
    )

    channelid = 1
    loggingchannel = bot.get_channel(channelid)
    embed = discord.Embed(title="Admin Logs | Warn", color=0xff0000)
    embed.add_field(name="Violating User:", value=f"{user.name} ({user.id})", inline=False)
    embed.add_field(name="Moderator:", value=f"{interaction.user.name} ({interaction.user.id})", inline=False)
    embed.add_field(name="Warnings", value=warnings[user_id], inline=False)
    embed.add_field(name="Reason", value=reason, inline=False)
    if proof:
        embed.set_image(url=proof.url)
    await loggingchannel.send(embed=embed)

    await asyncio.sleep(3)
    await interaction.delete_original_response()



@bot.tree.command(
    name="remove_warnings",
    description="Removes a specified number of warnings from a user.")
@app_commands.checks.has_any_role(*MODERATOR_ROLE_ID, *TRIAL_MODERATOR_ROLE_ID, "You don't have access to this command.")
async def remove_warnings(interaction: discord.Interaction,
                          user: discord.Member, amount: int):
    user_id = str(user.id)
    warnings = load_warnings()

    if user_id in warnings:
        warnings[user_id] = max(0, warnings[user_id] - amount)

    save_warnings(warnings)

    await interaction.response.send_message(
        f"{amount} warnings have been removed from {user.mention}. New warning count: {warnings[user_id]}"
    )

    channelid = 1
    loggingchannel = bot.get_channel(channelid)
    embed = discord.Embed(title="Admin Logs | Remove Warnings", color=0xff0000)
    embed.add_field(name="User: ", value=f"{user.name} ({user.id})", inline=False)
    embed.add_field(name="Moderator: ", value=f"{interaction.user.name} ({interaction.user.id})", inline=False)
    embed.add_field(name="Warnings: ", value=warnings[user_id], inline=False)
    await loggingchannel.send(embed=embed)

    await asyncio.sleep(3)
    await interaction.delete_original_response()


@bot.tree.command(name="reset_warnings", description="Resets all warnings for a user.")
@app_commands.checks.has_any_role(*MODERATOR_ROLE_ID, *TRIAL_MODERATOR_ROLE_ID, "You don't have access to this command.")
async def reset_warnings(interaction: discord.Interaction, user: discord.Member):
    user_id = str(user.id)
    warnings = load_warnings()

    if user_id in warnings:
        del warnings[user_id]
        warning_count = 0
    else:
        warning_count = "No warnings"

    save_warnings(warnings)

    await interaction.response.send_message(f"Warnings have been reset for {user.mention}.")

    channelid = 1
    loggingchannel = bot.get_channel(channelid)
    embed = discord.Embed(title="Admin Logs | Reset Warnings", color=0xff0000)
    embed.add_field(name="User: ", value=f"{user.name} ({user.id})", inline=False)
    embed.add_field(name="Moderator: ", value=f"{interaction.user.name} ({interaction.user.id})", inline=False)
    embed.add_field(name="Warnings: ", value=warning_count, inline=False)
    await loggingchannel.send(embed=embed)

    await asyncio.sleep(3)
    await interaction.delete_original_response()

@bot.tree.command(
    name="ping",
    description="Pings the bot and checks if it's online and its latency.")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(
        f"Pong! {round(bot.latency * 1000)}ms")

guild = discord.Object(id='1')


@bot.tree.command(name="killbot", description="Shuts down the bot for development.")
@commands.guild_only()
@commands.is_owner()
async def killbot(interaction: discord.Interaction):
    await interaction.response.send_message("Bot will be shutdown.")
    await bot.close()
    
@bot.command()
async def sync(ctx):
    if ctx.author.id == 1:
        await bot.tree.sync()
        await ctx.send('All Commands Synced.')
    else:
        print("Lmao")

def load_warnings():
    try:
        with open("data.json", "r") as file:
            return json.load(file)
    except FileNotFoundError:
        return {}


def save_warnings(warnings):
    with open("data.json", "w") as file:
        json.dump(warnings, file)


async def delete_user_messages(user):
    async for message in user.history(limit=None):
        await message.delete()


bot.run(TOKEN)
