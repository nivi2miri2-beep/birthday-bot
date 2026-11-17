import discord
from discord.ext import commands, tasks
from discord import app_commands, ui
import os
from datetime import datetime
import pytz
import asyncpg

# ================= قراءة المتغيرات من Railway =================
TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))
IMAGE_FILENAME = "birthday_banner.jpg"
# ===============================================================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

class BirthdayBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self.db = None

    async def setup_hook(self):
        try:
            self.db = await asyncpg.connect(DATABASE_URL)
            print("✅ تم الاتصال بقاعدة البيانات بنجاح!")
        except Exception as e:
            print(f"❌ خطأ في الاتصال بقاعدة البيانات: {e}")

        self.add_view(BirthdayRegisterView(self))
        await self.tree.sync()

bot = BirthdayBot()

def is_valid_date(day: int, month: int) -> bool:
    try:
        datetime(year=2024, month=month, day=day)
        return True
    except ValueError:
        return False

# ================= 1. قائمة اختيار الدول والمنطقة الزمنية =================
class TimezoneSelect(ui.Select):
    def __init__(self, bot_instance, day: int, month: int):
        self.bot_instance = bot_instance
        self.day = day
        self.month = month

        options = [
            discord.SelectOption(label="المغرب", value="Africa/Casablanca", emoji="🇲🇦"),
            discord.SelectOption(label="السعودية", value="Asia/Riyadh", emoji="🇸🇦"),
            discord.SelectOption(label="الإمارات", value="Asia/Dubai", emoji="🇦🇪"),
            discord.SelectOption(label="لبنان", value="Asia/Beirut", emoji="🇱🇧"),
            discord.SelectOption(label="الجزائر", value="Africa/Algiers", emoji="🇩🇿"),
            discord.SelectOption(label="تونس", value="Africa/Tunis", emoji="🇹🇳"),
            discord.SelectOption(label="العراق", value="Asia/Baghdad", emoji="🇮🇶"),
            discord.SelectOption(label="سوريا", value="Asia/Damascus", emoji="🇸🇾"),
            discord.SelectOption(label="الأردن", value="Asia/Amman", emoji="🇯🇴"),
            discord.SelectOption(label="فلسطين", value="Asia/Jerusalem", emoji="🇵🇸"),
            discord.SelectOption(label="مصر", value="Africa/Cairo", emoji="🇪🇬"),
            discord.SelectOption(label="توقيت غرينتش (UTC)", value="UTC", emoji="🌍")
        ]
        super().__init__(placeholder="اختر دولتك من القائمة...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        selected_timezone = self.values[0]
        user_id = str(interaction.user.id)
        guild_id = str(interaction.guild.id)

        try:
            existing = await self.bot_instance.db.fetchrow(
                "SELECT birth_day, birth_month FROM birthdays WHERE user_id = $1 AND guild_id = $2",
                user_id, guild_id
            )

            if existing:
                return await interaction.response.send_message(
                    f"❌ لقد قمت مسبقاً بتسجيل تاريخ ميلادك ({existing['birth_day']:02d}/{existing['birth_month']:02d}). للتعديل استعمل `/change_birthday`.",
                    ephemeral=True
                )

            await self.bot_instance.db.execute("""
                INSERT INTO birthdays (user_id, guild_id, birth_day, birth_month, timezone, last_wished_year)
                VALUES ($1, $2, $3, $4, $5, 0)
            """, user_id, guild_id, self.day, self.month, selected_timezone)

            await interaction.response.edit_message(
                content=f"✅ تم حفظ تاريخ ميلادك **{self.day:02d}/{self.month:02d}** وتحديد دولتك بنجاح! 🎂",
                view=None
            )
        except Exception as e:
            await interaction.response.send_message("❌ حدث خطأ أثناء الحفظ في قاعدة البيانات.", ephemeral=True)
            print(e)

class TimezoneView(ui.View):
    def __init__(self, bot_instance, day: int, month: int):
        super().__init__(timeout=60)
        self.add_item(TimezoneSelect(bot_instance, day, month))

# ================= 2. نافذة إدخال التاريخ (Modal) =================
class BirthdayModal(ui.Modal, title="تسجيل تاريخ الميلاد 🎂"):
    def __init__(self, bot_instance):
        super().__init__()
        self.bot_instance = bot_instance

    month_input = ui.TextInput(
        label="الشهر (Month)",
        placeholder="مثال: 5 أو 11",
        min_length=1,
        max_length=2,
        required=True
    )
    day_input = ui.TextInput(
        label="اليوم (Day)",
        placeholder="مثال: 9 أو 24",
        min_length=1,
        max_length=2,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            month = int(self.month_input.value.strip())
            day = int(self.day_input.value.strip())
        except ValueError:
            return await interaction.response.send_message(
                "❌ عذراً، يرجى إدخال أرقام صحيحة للشهر واليوم.", ephemeral=True
            )

        if not is_valid_date(day, month):
            return await interaction.response.send_message(
                "❌ هذا التاريخ غير موجود! يرجى التحقق من الشهر واليوم.", ephemeral=True
            )

        view = TimezoneView(self.bot_instance, day, month)
        await interaction.response.send_message(
            f"📅 لقد اخترت تاريخ: **{day:02d}/{month:02d}**.\nالمرجو **اختيار دولتك** من القائمة أدناه لكي تصلك التهنئة في منتصف الليل بالتوقيت المحلي لبلدك بدقة:",
            view=view,
            ephemeral=True
        )

class BirthdayRegisterView(ui.View):
    def __init__(self, bot_instance):
        super().__init__(timeout=None)
        self.bot_instance = bot_instance

    @ui.button(
        label="تسجيل عيد الميلاد 🎂",
        style=discord.ButtonStyle.secondary,
        custom_id="register_birthday_btn"
    )
    async def register_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(BirthdayModal(self.bot_instance))
        # ================= 3. أمر !setup_birthday (للمشرفين) =================
@bot.command(name="setup_birthday")
@commands.has_permissions(administrator=True)
async def setup_birthday(ctx: commands.Context):
    try:
        await ctx.message.delete()
    except discord.Forbidden:
        pass

    embed = discord.Embed(
        title="Birthday Registration 🎂",
        description=(
            "Want Eternal World to 🤍 celebrate your special day?\n\n"
            "اضغط على الزر بالأسفل لتسجيل تاريخ ميلادك!\n\n"
            "Birthday Star 🌟"
        ),
        color=0x2B2D31
    )
    await ctx.send(embed=embed, view=BirthdayRegisterView(bot))

# ================= 4. سلاش كوماند /wish =================
@bot.tree.command(name="wish", description="إرسال تهنئة خاصة لعضو بمناسبة عيد ميلاده 🎂")
@app_commands.describe(
    member="اختر العضو الذي ترغب في تهنئته",
    message="اكتب رسالة التهنئة هنا"
)
async def wish_command(interaction: discord.Interaction, member: discord.Member, message: str):
    if member.bot:
        return await interaction.response.send_message("❌ لا يمكنك إرسال تهنئة إلى بوت!", ephemeral=True)

    embed = discord.Embed(
        title="💌 تهنئة خاصة بمناسبة عيد الميلاد!",
        description=f"« {message} »",
        color=0xFFC0CB
    )
    embed.set_footer(text=f"من طرف: {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)

    await interaction.response.send_message(
        content=f"🎉 {member.mention} وصلتْك تهنئة مميزة من {interaction.user.mention}!",
        embed=embed
    )

# ================= 5. سلاش كوماند /set_birthday =================
@bot.tree.command(name="set_birthday", description="إضافة تاريخ ميلاد أي عضو في السيرفر 📅")
@app_commands.describe(
    member="العضو المراد تسجيل عيد ميلاده",
    day="اليوم (مثال: 15)",
    month="الشهر (مثال: 8)"
)
async def set_birthday_command(interaction: discord.Interaction, member: discord.Member, day: int, month: int):
    if member.bot:
        return await interaction.response.send_message("❌ لا يمكنك تسجيل عيد ميلاد للبوتات!", ephemeral=True)

    if not is_valid_date(day, month):
        return await interaction.response.send_message("❌ هذا التاريخ غير صحيح! يرجى التأكد.", ephemeral=True)

    if not bot.db:
        return await interaction.response.send_message("❌ قاعدة البيانات غير متصلة حالياً.", ephemeral=True)

    try:
        user_id = str(member.id)
        guild_id = str(interaction.guild.id)

        existing = await bot.db.fetchrow(
            "SELECT birth_day, birth_month FROM birthdays WHERE user_id = $1 AND guild_id = $2",
            user_id, guild_id
        )

        if existing:
            return await interaction.response.send_message(
                f"❌ هذا العضو مسجل مسبقاً بالتاريخ ({existing['birth_day']:02d}/{existing['birth_month']:02d}).",
                ephemeral=True
            )

        await bot.db.execute("""
            INSERT INTO birthdays (user_id, guild_id, birth_day, birth_month, timezone, last_wished_year)
            VALUES ($1, $2, $3, $4, 'Africa/Casablanca', 0)
        """, user_id, guild_id, day, month)

        await interaction.response.send_message(
            f"✅ تم بنجاح تسجيل تاريخ ميلاد العضو {member.mention} في **{day:02d}/{month:02d}** (بالتوقيت الافتراضي) 🎂",
            ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message("❌ حدث خطأ أثناء الحفظ.", ephemeral=True)
        print(e)

# ================= 6. سلاش كوماند /change_birthday =================
@bot.tree.command(name="change_birthday", description="تعديل وتغيير تاريخ ميلادك المسجل مسبقاً 🔄")
@app_commands.describe(
    day="اليوم الجديد",
    month="الشهر الجديد"
)
async def change_birthday_command(interaction: discord.Interaction, day: int, month: int):
    if not is_valid_date(day, month):
        return await interaction.response.send_message("❌ هذا التاريخ غير صحيح!", ephemeral=True)

    if not bot.db:
        return await interaction.response.send_message("❌ قاعدة البيانات غير متصلة حالياً.", ephemeral=True)

    user_id = str(interaction.user.id)
    guild_id = str(interaction.guild.id)

    try:
        result = await bot.db.execute("""
            UPDATE birthdays 
            SET birth_day = $1, birth_month = $2 
            WHERE user_id = $3 AND guild_id = $4
        """, day, month, user_id, guild_id)

        if result == "UPDATE 0":
            return await interaction.response.send_message(
                "❌ ليس لديك تاريخ ميلاد مسجل أصلاً!",
                ephemeral=True
            )

        await interaction.response.send_message(
            f"✅ تم تحديث تاريخ ميلادك بنجاح إلى: **{day:02d}/{month:02d}** 🔄",
            ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message("❌ حدث خطأ أثناء التعديل.", ephemeral=True)
        print(e)

# ================= 7. الفحص الأوتوماتيكي (حسب توقيت كل دولة) =================
@tasks.loop(minutes=1)
async def check_birthdays():
    if not bot.db:
        return

    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        return

    guild = channel.guild
    guild_id = str(guild.id)

    rows = await bot.db.fetch(
        "SELECT user_id, birth_day, birth_month, timezone, last_wished_year FROM birthdays WHERE guild_id = $1",
        guild_id
    )

    for row in rows:
        user_id = row["user_id"]
        day = row["birth_day"]
        month = row["birth_month"]
        tz_name = row["timezone"] or "Africa/Casablanca"
        last_wished_year = row["last_wished_year"]

        try:
            user_tz = pytz.timezone(tz_name)
        except pytz.UnknownTimeZoneError:
            user_tz = pytz.timezone("Africa/Casablanca")

        now_user = datetime.now(user_tz)

        if now_user.hour == 0 and now_user.minute == 0:
            member = guild.get_member(int(user_id))
            if not member:
                continue

            is_today = (day == now_user.day and month == now_user.month)

            if is_today and last_wished_year != now_user.year:
                await bot.db.execute(
                    "UPDATE birthdays SET last_wished_year = $1 WHERE user_id = $2 AND guild_id = $3",
                    now_user.year, user_id, guild_id
                )

                birthday_text = (
                    "🎂 عيد ميلاد سعيد يا نجمنا!\n\n"
                    "اليوم ليس يوماً عادياً في Eternal World، اليوم نحتفل بأحد أعضاء عائلتنا الغالية! 🤍\n\n"
                    "كل عام وأنت بخير، ونتمنى لك سنة جديدة مليئة بالأيام الجميلة، والتجارب التي تستحق أن تُعاش، والذكريات التي تستحق أن تبقى.\n\n"
                    "نحن سعداء بوجودك بيننا، ونتمنى أن يحمل لك عامك الجديد الكثير مما تحب وتتمنى.\n\n"
                    "استمتع بيومك، فأنت نجم احتفالنا اليوم! ✨\n\n"
                    "من عائلة Eternal World، بكل الحب. 🤍"
                )

                embed = discord.Embed(
                    description=birthday_text,
                    color=0xFFC0CB
                )

                content_mentions = f"@everyone | {member.mention}"

                if os.path.exists(IMAGE_FILENAME):
                    file = discord.File(IMAGE_FILENAME, filename="happy_birthday.jpg")
                    embed.set_image(url="attachment://happy_birthday.jpg")
                    await channel.send(content=content_mentions, embed=embed, file=file)
                else:
                    await channel.send(content=content_mentions, embed=embed)

@check_birthdays.before_loop
async def before_check():
    await bot.wait_until_ready()

@bot.event
async def on_ready():
    print(f"✅ البوت يعمل الآن باسم: {bot.user}")
    if not check_birthdays.is_running():
        check_birthdays.start()

bot.run(TOKEN)
    
