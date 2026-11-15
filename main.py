import os
import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncpg
from datetime import datetime
from zoneinfo import ZoneInfo, available_timezones

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

DATABASE_URL = os.getenv("DATABASE_URL")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))

db_pool = None

@bot.event
async def on_ready():
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL)
    
    # Zdna timezone column f database ila makantsch
    async with db_pool.acquire() as connection:
        await connection.execute("""
            CREATE TABLE IF NOT EXISTS birthdays (
                id SERIAL PRIMARY KEY,
                user_id VARCHAR(50) NOT NULL,
                guild_id VARCHAR(50) NOT NULL,
                birth_day INT NOT NULL,
                birth_month INT NOT NULL,
                timezone VARCHAR(100) DEFAULT 'Africa/Casablanca',
                last_wished_year INT DEFAULT 0,
                UNIQUE(user_id, guild_id)
            );
        """)
    
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands.")
    except Exception as e:
        print(e)
        
    # N-reddouha t-cheki kol sa3a (Hourly) machi ghir kol nhar, bach n-chofo wach wslat 12 f ay tanzim
    check_birthdays.start()
    print(f"Bot {bot.user} is online and ready with Timezones!")

# ==================== 1. SETUP BIRTHDAY WITH TIMEZONE ====================
class BirthdayModal(discord.ui.Modal, title="تسجيل عيد الميلاد 🎂"):
    day = discord.ui.TextInput(label="اليوم (1-31)", placeholder="مثال: 15", max_length=2)
    month = discord.ui.TextInput(label="الشهر (1-12)", placeholder="مثال: 11", max_length=2)
    tz = discord.ui.TextInput(label="المنطقة الزمنية (Timezone)", placeholder="مثال: Asia/Beirut أو Africa/Casablanca", default="Africa/Casablanca")

    async def on_submit(self, interaction: discord.Interaction):
        try:
            d = int(self.day.value)
            m = int(self.month.value)
            user_tz = self.tz.value.strip()
            
            # Vérification wach timezone s7iha
            if user_tz not in available_timezones():
                raise ValueError("Invalid Timezone")
                
            if not (1 <= d <= 31 and 1 <= m <= 12):
                raise ValueError()
        except ValueError:
            await interaction.response.send_message("❌ التاريخ أو Timezone غير صحيح! (مثال لـ لبنان: Asia/Beirut، المغرب: Africa/Casablanca)", ephemeral=True)
            return

        async with db_pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO birthdays (user_id, guild_id, birth_day, birth_month, timezone)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (user_id, guild_id) 
                DO UPDATE SET birth_day = EXCLUDED.birth_day, birth_month = EXCLUDED.birth_month, timezone = EXCLUDED.timezone;
            """, str(interaction.user.id), str(interaction.guild_id), d, m, user_tz)

        await interaction.response.send_message(f"✅ تم تسجيل عيد ميلادك بنجاح في {d}/{m} بتوقيت {user_tz}!", ephemeral=True)

class BirthdayView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="تسجيل عيد الميلاد 🎂", style=discord.ButtonStyle.blurple, custom_id="setup_birthday_btn")
    async def birthday_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BirthdayModal())

@bot.command(name="setup_birthday")
async def setup_birthday(ctx):
    embed = discord.Embed(
        title="Birthday Registration 🎂",
        description="Want Eternal World to 🤍 celebrate your special day?\n\nاضغط على الزر بالأسفل لتسجيل تاريخ ميلادك مع توقيت بلادك!",
        color=0xffb6c1
    )
    embed.set_footer(text="Birthday Star 🌟")
    view = BirthdayView()
    await ctx.send(embed=embed, view=view)
    try:
        await ctx.message.delete()
    except:
        pass


# ==================== 2. ADD BIRTHDAY (SURPRISE) WITH TIMEZONE ====================
@bot.tree.command(name="add_birthday", description="إضافة عيد ميلاد شخص آخر مفاجأة مع تحديد توقيت بلده")
@app_commands.describe(member="الشخص المعني", day="اليوم (1-31)", month="الشهر (1-12)", timezone="مثال: Asia/Beirut أو Africa/Casablanca")
async def add_birthday(interaction: discord.Interaction, member: discord.Member, day: int, month: int, timezone: str = "Africa/Casablanca"):
    if timezone not in available_timezones():
        await interaction.response.send_message("❌ Timezone غير صحيحة! تأكد من كتابتها بشكل صحيح (مثال: Asia/Beirut)", ephemeral=True)
        return

    if not (1 <= day <= 31 and 1 <= month <= 12):
        await interaction.response.send_message("❌ التاريخ غير صحيح!", ephemeral=True)
        return

    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO birthdays (user_id, guild_id, birth_day, birth_month, timezone)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (user_id, guild_id) 
            DO UPDATE SET birth_day = EXCLUDED.birth_day, birth_month = EXCLUDED.birth_month, timezone = EXCLUDED.timezone;
        """, str(member.id), str(interaction.guild_id), day, month, timezone)

    await interaction.response.send_message(f"🤫 تمت إضافة عيد ميلاد {member.mention} بنجاح في {day}/{month} بتوقيت {timezone} (مفاجأة!)", ephemeral=True)


# ==================== 3. CUSTOM WISH COMMAND ====================
@bot.tree.command(name="wish", description="كتابة تهنئة مخصصة لشخص في عيد ميلاده وتطاكيه مع everyone")
@app_commands.describe(member="صاحب عيد الميلاد", custom_message="التهنئة التي تريد كتابتها", image_url="رابط الصورة")
async def wish(interaction: discord.Interaction, member: discord.Member, custom_message: str, image_url: str):
    channel = bot.get_channel(CHANNEL_ID) or interaction.channel
    content = f"@everyone 🎂 عيد ميلاد سعيد يا نجمنا!\n\n{custom_message}\n\n{member.mention}"
    
    await channel.send(content=content)
    await channel.send(image_url)
    await interaction.response.send_message("✅ تم إرسال التهنئة بنجاح!", ephemeral=True)


# ==================== 4. AUTOMATIC CHECKER HOURLY (BY LOCAL TIME) ====================
@tasks.loop(hours=1) # Kat-cheki kol sa3a bach t-dir 12:00 dyal lil f kol blasa b zabt
async def check_birthdays():
    if not db_pool:
        return

    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id, guild_id, birth_day, birth_month, timezone, last_wished_year FROM birthdays;")

        for row in rows:
            try:
                user_tz = ZoneInfo(row['timezone'])
            except:
                user_tz = ZoneInfo("Africa/Casablanca") # Default
                
            # Now f l-waqt l-maHalli dyal dik l-bnt
            now_local = datetime.now(user_tz)
            
            current_day = now_local.day
            current_month = now_local.month
            current_year = now_local.year
            current_hour = now_local.hour
            current_minute = now_local.minute

            # Wach l-youm howa 3id miladha W Dba m-zbit 00:00 (12 dyal lil f bladha)?
            if row['birth_day'] == current_day and row['birth_month'] == current_month:
                if row['last_wished_year'] == current_year:
                    continue # Saf tahnia f nafs l-3am
                
                # Ntsnaw tal 12:00 wla 12:59 (f awl sa3a f nhar l-3id)
                if current_hour == 0:
                    guild = bot.get_guild(int(row['guild_id']))
                    if not guild:
                        continue
                    
                    member = guild.get_member(int(row['user_id']))
                    if not member:
                        try:
                            member = await guild.fetch_member(int(row['user_id']))
                        except:
                            continue

                    channel = guild.get_channel(CHANNEL_ID)
                    if not channel:
                        for c in guild.text_channels:
                            if c.permissions_for(guild.me).send_messages:
                                channel = c
                                break

                    if channel:
                        text_content = (
                            f"@everyone 🎂 عيد ميلاد سعيد يا نجمنا!\n\n"
                            f"اليوم مو يوم عادي في Eternal World، اليوم نحتفل بأحد أفراد عائلتنا! 🤍\n\n"
                            f"كل عام وأنت بخير، ونتمنى لك سنة جديدة مليئة بالأيام الجميلة، والتجارب التي تستحق أن تُعاش، والذكريات التي تستحق أن تبقى.\n\n"
                            f"نحن سعداء بوجودك بيننا، ونتمنى أن يحمل لك عامك الجديد الكثير مما تحب وتتمنى.\n\n"
                            f"استمتع بيومك، فأنت نجم احتفالنا اليوم! ✨\n\n"
                            f"من عائلة Eternal World، بكل الحب. 🤍\n\n"
                            f"{member.mention}"
                        )
                        
                        # Tswira dyal l-qetat (bdelha ila bghiti b rabet akhor)
                        image_link = "https://images-ext-1.discordapp.net/external/..." 
                        
                        await channel.send(text_content)
                        await channel.send(image_link)

                        # Update last wished year
                        await conn.execute("""
                            UPDATE birthdays SET last_wished_year = $1 
                            WHERE user_id = $2 AND guild_id = $3;
                        """, current_year, row['user_id'], row['guild_id'])

@check_birthdays.before_loop
async def before_check():
    await bot.wait_until_ready()

TOKEN = os.getenv("TOKEN")
bot.run(TOKEN)
  
