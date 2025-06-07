import discord
from discord.ext import commands
from supabase import create_client, Client
from datetime import datetime
import pytz
import os
from dotenv import load_dotenv
from flask import Flask
import threading

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

if not SUPABASE_URL or not SUPABASE_KEY or not DISCORD_TOKEN:
    raise Exception("Missing SUPABASE_URL, SUPABASE_KEY, or DISCORD_TOKEN in environment variables")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
IST = pytz.timezone("Asia/Kolkata")

# ---------- USER STREAKS ----------
def get_streak(user_id: str) -> int:
    res = supabase.table("streaks").select("streak").eq("user_id", user_id).execute()
    if res.data and len(res.data) > 0:
        return res.data[0]["streak"]
    return 0

def increment_streak(user_id: str) -> bool:
    now = datetime.now(IST)

    # Define today's 9 PM and yesterday's 9 PM
    today_9pm = now.replace(hour=21, minute=0, second=0, microsecond=0)
    if now < today_9pm:
        # If current time is before today 9 PM, the window started yesterday 9 PM
        window_start = today_9pm.replace(day=today_9pm.day - 1)
    else:
        # If current time is after 9 PM, window starts today at 9 PM
        window_start = today_9pm

    res = supabase.table("streaks").select("*").eq("user_id", user_id).execute()

    if res.data and len(res.data) > 0:
        last_updated_str = res.data[0].get("last_updated")
        if last_updated_str:
            last_updated = datetime.fromisoformat(last_updated_str).astimezone(IST)

            # Deny if user already checked in within this 9PM–9PM window
            if last_updated >= window_start:
                return False

        # Allow increment
        new_streak = res.data[0]["streak"] + 1
        supabase.table("streaks").update({
            "streak": new_streak,
            "last_updated": now.isoformat()
        }).eq("user_id", user_id).execute()
        return True
    else:
        # New user — only allow if after 9 PM
        if now < today_9pm:
            return False
        supabase.table("streaks").insert({
            "user_id": user_id,
            "streak": 1,
            "last_updated": now.isoformat()
        }).execute()
        return True


def reset_streak(user_id: str):
    exists = get_streak(user_id)
    if exists is not None:
        supabase.table("streaks").update({
            "streak": 0,
            "last_updated": datetime.now(IST).isoformat()
        }).eq("user_id", user_id).execute()
    else:
        supabase.table("streaks").insert({
            "user_id": user_id,
            "streak": 0,
            "last_updated": datetime.now(IST).isoformat()
        }).execute()

# ---------- SERVER CONFIG ----------
def set_config(channel_id: int, role_id: int):
    supabase.table("config").upsert({
        "id": 1,
        "channel_id": channel_id,
        "role_id": role_id
    }).execute()

def get_config():
    res = supabase.table("config").select("*").eq("id", 1).execute()
    if res.data and len(res.data) > 0:
        return res.data[0]
    return None

# ---------- FLASK WEB SERVER ----------
app = Flask("")

@app.route("/")
def home():
    return "Bot is running!"

def run_webserver():
    port = int(os.getenv("PORT", 8000))
    app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_webserver).start()

# ---------- DISCORD BOT ----------
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f'✅ Logged in as {bot.user.name}')

# Manual Setup Command
@bot.command()
@commands.has_permissions(administrator=True)
async def setup(ctx):
    await ctx.send("Mention the channel for daily reports (e.g., #nofap):")

    def check_channel(m): 
        return m.author == ctx.author and m.channel == ctx.channel

    channel_msg = await bot.wait_for("message", check=check_channel)

    if not channel_msg.channel_mentions:
        await ctx.send("❌ No channel mentioned. Please try again.")
        return

    channel_id = channel_msg.channel_mentions[0].id

    await ctx.send("Mention the role to be pinged daily (e.g., @NoFap):")

    def check_role(m): 
        return m.author == ctx.author and m.channel == ctx.channel

    role_msg = await bot.wait_for("message", check=check_role)

    if not role_msg.role_mentions:
        await ctx.send("❌ No role mentioned. Please try again.")
        return

    role_id = role_msg.role_mentions[0].id

    set_config(channel_id, role_id)
    await ctx.send("✅ Setup complete. You can now use the bot.")

# Commands
@bot.command()
async def streakon(ctx):
    success = increment_streak(str(ctx.author.id))
    if success:
        streak = get_streak(str(ctx.author.id))
        await ctx.send(f"✅ {ctx.author.mention} Streak updated! Current streak: **{streak} days** 💪")
    else:
        await ctx.send(f"⚠️ {ctx.author.mention} You’ve already checked in today. Try again tomorrow!")

@bot.command()
async def streakbroken(ctx):
    reset_streak(str(ctx.author.id))
    await ctx.send(f"❌ {ctx.author.mention} Your streak has been reset to 0. Let's restart 🔁")

@bot.command()
async def nightfall(ctx):
    streak = get_streak(str(ctx.author.id))
    await ctx.send(
        f"🌙 {ctx.author.mention} It is fine, don't feel guilty. It is a natural process. No loss.\n🔥 Your streak remains: **{streak} days**"
    )

@bot.command()
async def leaderboard(ctx):
    res = supabase.table("streaks").select("*").order("streak", desc=True).execute()
    if not res.data:
        await ctx.send("No data found in leaderboard.")
        return

    message = "**🏆 NoFap Leaderboard 🏆**\n\n"
    for i, user in enumerate(res.data[:10], start=1):
        try:
            user_obj = await bot.fetch_user(int(user["user_id"]))
            username = user_obj.name
        except:
            username = f"User ID {user['user_id']}"
        message += f"**#{i}** - {username} — **{user['streak']}** days\n"

    await ctx.send(message)

# Sapphire Bot Message Listener
@bot.event
async def on_message(message):
    if message.author.id == bot.user.id:
        return

    SAPPHIRE_ID = 678344927997853742

    if message.author.id == SAPPHIRE_ID:
        if message.mentions:
            mentioned_user = message.mentions[0]
            user_id = str(mentioned_user.id)

            if "!streakon" in message.content:
                success = increment_streak(user_id)
                if success:
                    streak = get_streak(user_id)
                    await message.channel.send(f"✅ {mentioned_user.mention} Streak updated! Current streak: **{streak} days** 💪")
                else:
                    await message.channel.send(f"⚠️ {mentioned_user.mention} You’ve already checked in today. Try again tomorrow!")

            elif "!streakbroken" in message.content or "!justdone" in message.content:
                reset_streak(user_id)
                await message.channel.send(f"❌ {mentioned_user.mention} Your streak has been reset to 0. Let's restart 🔁")

            elif "!nightfall" in message.content:
                streak = get_streak(user_id)
                await message.channel.send(f"🌙 {mentioned_user.mention} It is fine, don't feel guilty. It is a natural process. No loss.\n🔥 Your streak remains: **{streak} days**")

            elif "!leaderboard" in message.content:
                res = supabase.table("streaks").select("*").order("streak", desc=True).execute()
                if not res.data:
                    await message.channel.send("No data found in leaderboard.")
                    return

                response = "**🏆 NoFap Leaderboard 🏆**\n\n"
                for i, user in enumerate(res.data[:10], start=1):
                    try:
                        user_obj = await bot.fetch_user(int(user["user_id"]))
                        username = user_obj.name
                    except:
                        username = f"User ID {user['user_id']}"
                    response += f"**#{i}** - {username} — **{user['streak']}** days\n"

                await message.channel.send(response)

    await bot.process_commands(message)

bot.run(DISCORD_TOKEN)
