import discord
from discord.ext import commands, tasks
from supabase import create_client, Client
from datetime import datetime
import pytz
import os
from dotenv import load_dotenv

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
    today = datetime.now(IST).date()
    res = supabase.table("streaks").select("*").eq("user_id", user_id).execute()

    if res.data and len(res.data) > 0:
        last_updated = res.data[0].get("last_updated")
        if last_updated:
            last_date = datetime.fromisoformat(last_updated).astimezone(IST).date()
            if last_date == today:
                return False  # Already incremented today

        new_streak = res.data[0]["streak"] + 1
        supabase.table("streaks").update({
            "streak": new_streak,
            "last_updated": datetime.now(IST).isoformat()
        }).eq("user_id", user_id).execute()
        return True
    else:
        supabase.table("streaks").insert({
            "user_id": user_id,
            "streak": 1,
            "last_updated": datetime.now(IST).isoformat()
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
    daily_post.start()

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
    await ctx.send("✅ Setup complete. Daily reports will be sent.")

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

@bot.command()
@commands.has_permissions(administrator=True)
async def testpost(ctx):
    config = get_config()
    if not config:
        await ctx.send("❌ Configuration not set. Use `!setup` first.")
        return

    channel = bot.get_channel(int(config['channel_id']))
    role_id = config['role_id']
    now = datetime.now(IST)

    if not channel:
        await ctx.send("❌ Could not find the configured channel.")
        return

    await channel.send(f"<@&{role_id}>")
    await channel.send(
        f"**✅ Test Report {now.strftime('%d %B %Y %H:%M')}**\n"
        "Type:\n"
        "`!streakon` - If you're on track ✅\n"
        "`!streakbroken` - If streak is broken ❌\n"
        "`!nightfall` - For nightfall only 🌙\n"
        "`!leaderboard` - See top streaks 🔁"
    )
    await ctx.send("✅ Test post sent!")

@tasks.loop(minutes=1)
async def daily_post():
    now = datetime.now(IST)
    if now.hour == 23 and now.minute == 0:
        config = get_config()
        if not config:
            return
        channel = bot.get_channel(int(config['channel_id']))
        role_id = config['role_id']

        if not channel:
            return

        await channel.send(f"<@&{role_id}>")
        await channel.send(
            f"**📅 Daily Check-in {now.strftime('%d %B %Y %H:%M')}**\n"
            "Type:\n"
            "`!streakon` - If you're on track ✅\n"
            "`!streakbroken` - If streak is broken ❌\n"
            "`!nightfall` - For nightfall only 🌙\n"
            "`!leaderboard` - See top streaks 🔁"
        )

bot.run(DISCORD_TOKEN)
