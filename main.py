import discord
from discord.ext import commands, tasks
from discord import app_commands, ui
import os
import time
from datetime import datetime
import pytz
import asyncpg

# ================= قراءة المتغيرات من Railway =================
TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))
TARGET_CHANNEL_ID = int(os.getenv("TARGET_CHANNEL_ID", "1569523433514205254"))
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
IMAGE_FILENAME = "birthday_banner.jpg"
# ===============================================================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

MEMBER_BIRTHDAY_TEXT = (
    "🎂 عيد ميلاد سعيد يا نجمنا!\n\n"
    "اليوم ليس يوماً عادياً في Eternal World، اليوم نحتفل بأحد أعضاء عائلتنا الغالية! 🤍\n\n"
    "كل عام وأنت بخير، ونتمنى لك سنة جديدة مليئة بالأيام الجميلة، والتجارب التي تستحق أن تُعاش، والذكريات التي تستحق أن تبقى.\n\n"
    "نحن سعداء بوجودك بيننا، ونتمنى أن يحمل لك عامك الجديد الكثير مما تحب وتتمنى.\n\n"
    "استمتع بيومك، فأنت نجم احتفالنا اليوم! ✨\n\n"
    "من عائلة Eternal World، بكل الحب. 🤍"
)

def build_tulpa_birthday_text(tulpa_name: str, member_mention: str) -> str:
    return (
        f"˚₊· ͟͟͞͞➳❥ 🌸 **✦ عيد ميلاد سعيد يا {tulpa_name} ✦** 🌸 ˚₊· ͟͟͞͞➳❥\n"
        "⋆｡ﾟ☁︎｡⋆｡ ﾟ☾ ﾟ｡⋆\n\n"
        f"ʚĭɞ اليوم يحمل فرحة خاصة في **Eternal World**، ونحن نشارك {member_mention} الاحتفاء بيوم ميلادك الجميل! ✨🌷\n\n"
        "ʚĭɞ كل عام وأنت بخير، ونتمنى لكما معاً أياماً مليئة بالدفء والسكينة، ولحظاتٍ لا تُنسى، وحضوراً يزداد إشراقاً ووضوحاً يوماً بعد يوم. 🤍🫧\n\n"
        "ʚĭɞ وجودك يضيف معنىً جميلاً، واليوم هو يومك لتتألق في عالمنا الصغير بكل محبة ولطف! 🎀🌸\n\n"
        "⋆｡ﾟ☁︎｡⋆｡ ﾟ☾ ﾟ｡⋆\n"
        "*✶ من عائلة Eternal World. 🤍*"
    )

TIMEZONE_OPTIONS = [
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
    discord.SelectOption(label="توقيت غرينتش (UTC)", value="UTC", emoji="🌍"),
]

class BirthdayBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self.db = None

    async def ensure_db(self):
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL is not set")
        if self.db is None or self.db.is_closed():
            self.db = await asyncpg.connect(DATABASE_URL)
        return self.db

    async def ensure_schema(self):
        db = await self.ensure_db()
        await db.execute("""
            ALTER TABLE birthdays
            ADD COLUMN IF NOT EXISTS entry_type TEXT NOT NULL DEFAULT 'member',
            ADD COLUMN IF NOT EXISTS tulpa_name TEXT
        """)

    async def setup_hook(self):
        try:
            await self.ensure_db()
            await self.ensure_schema()
            print("✅ تم الاتصال بقاعدة البيانات وتحديث الأعمدة بنجاح!")
        except Exception as e:
            print(f"❌ خطأ في الاتصال بقاعدة البيانات: {e}")

        self.add_view(BirthdayRegisterView(self))
        self.add_view(TulpaRegisterView(self))
        await self.tree.sync()

bot = BirthdayBot()

def is_valid_date(day: int, month: int) -> bool:
    try:
        datetime(year=2024, month=month, day=day)
        return True
    except ValueError:
        return False

def is_owner_or_admin(interaction: discord.Interaction) -> bool:
    if OWNER_ID != 0 and interaction.user.id == OWNER_ID:
        return True
    return bool(interaction.user.guild_permissions.administrator)

# ================= 1. قائمة اختيار الدول والمنطقة الزمنية (للعضو) =================
class TimezoneSelect(ui.Select):
    def __init__(self, bot_instance, day: int, month: int):
        self.bot_instance = bot_instance
        self.day = day
        self.month = month
        super().__init__(
            placeholder="اختر دولتك من القائمة...",
            min_values=1,
            max_values=1,
            options=TIMEZONE_OPTIONS,
        )

    async def callback(self, interaction: discord.Interaction):
        selected_timezone = self.values[0]
        user_id = str(interaction.user.id)
        guild_id = str(interaction.guild.id)

        try:
            db = await self.bot_instance.ensure_db()
            existing = await db.fetchrow(
                """
                SELECT birth_day, birth_month FROM birthdays
                WHERE user_id = $1 AND guild_id = $2 AND COALESCE(entry_type, 'member') = 'member'
                """,
                user_id, guild_id
            )

            if existing:
                return await interaction.response.send_message(
                    f"❌ لقد قمت مسبقاً بتسجيل تاريخ ميلادك ({existing['birth_day']:02d}/{existing['birth_month']:02d}). للتعديل استعمل `/change_birthday`.",
                    ephemeral=True
                )

            await db.execute("""
                INSERT INTO birthdays (user_id, guild_id, birth_day, birth_month, timezone, last_wished_year, entry_type, tulpa_name)
                VALUES ($1, $2, $3, $4, $5, 0, 'member', NULL)
            """, user_id, guild_id, self.day, self.month, selected_timezone)

            await interaction.response.edit_message(
                content=f"✅ تم حفظ تاريخ ميلادك **{self.day:02d}/{self.month:02d}** وتحديد دولتك بنجاح! 🎂",
                view=None
            )
        except Exception as e:
            await interaction.response.send_message("❌ حدث خطأ أثناء الحفظ في قاعدة البيانات.", ephemeral=True)
            print("Register DB error:", e)

class TimezoneView(ui.View):
    def __init__(self, bot_instance, day: int, month: int):
        super().__init__(timeout=60)
        self.add_item(TimezoneSelect(bot_instance, day, month))

# ================= 1B. قائمة اختيار الدول والمنطقة الزمنية (للتولبا) =================
class TulpaTimezoneSelect(ui.Select):
    def __init__(self, bot_instance, tulpa_name: str, day: int, month: int):
        self.bot_instance = bot_instance
        self.tulpa_name = tulpa_name
        self.day = day
        self.month = month
        super().__init__(
            placeholder="اختر دولة التولبا من القائمة...",
            min_values=1,
            max_values=1,
            options=TIMEZONE_OPTIONS,
        )

    async def callback(self, interaction: discord.Interaction):
        selected_timezone = self.values[0]
        user_id = str(interaction.user.id)
        guild_id = str(interaction.guild.id)

        try:
            db = await self.bot_instance.ensure_db()
            existing = await db.fetchrow(
                """
                SELECT birth_day, birth_month FROM birthdays
                WHERE user_id = $1 AND guild_id = $2
                  AND entry_type = 'tulpa'
                  AND LOWER(tulpa_name) = LOWER($3)
                """,
                user_id, guild_id, self.tulpa_name
            )

            if existing:
                return await interaction.response.send_message(
                    f"❌ التولبا **{self.tulpa_name}** مسجلة مسبقاً في ({existing['birth_day']:02d}/{existing['birth_month']:02d}). لتعديلها استعمل `/change_birthday`.",
                    ephemeral=True
                )

            await db.execute("""
                INSERT INTO birthdays (user_id, guild_id, birth_day, birth_month, timezone, last_wished_year, entry_type, tulpa_name)
                VALUES ($1, $2, $3, $4, $5, 0, 'tulpa', $6)
            """, user_id, guild_id, self.day, self.month, selected_timezone, self.tulpa_name)

            await interaction.response.edit_message(
                content=f"✅ تم حفظ عيد ميلاد التولبا **🌸 {self.tulpa_name}** في **{self.day:02d}/{self.month:02d}** وتحديد الدولة بنجاح!",
                view=None
            )
        except Exception as e:
            await interaction.response.send_message("❌ حدث خطأ أثناء حفظ عيد ميلاد التولبا.", ephemeral=True)
            print("Tulpa register DB error:", e)

class TulpaTimezoneView(ui.View):
    def __init__(self, bot_instance, tulpa_name: str, day: int, month: int):
        super().__init__(timeout=60)
        self.add_item(TulpaTimezoneSelect(bot_instance, tulpa_name, day, month))

# ================= 2. نوافذ والأزرار المستقلة (للعضو وللتولبا) =================
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

class TulpaBirthdayModal(ui.Modal, title="تسجيل عيد ميلاد تولبا 🌸"):
    def __init__(self, bot_instance):
        super().__init__()
        self.bot_instance = bot_instance

    tulpa_name_input = ui.TextInput(
        label="اسم التولبا (Tulpa Name)",
        placeholder="اكتب اسم التولبا هنا...",
        min_length=1,
        max_length=50,
        required=True
    )
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
        tulpa_name = self.tulpa_name_input.value.strip()
        if not tulpa_name:
            return await interaction.response.send_message(
                "❌ يرجى إدخال اسم صحيح للتولبا.", ephemeral=True
            )

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

        view = TulpaTimezoneView(self.bot_instance, tulpa_name, day, month)
        await interaction.response.send_message(
            f"🌸 التولبا: **{tulpa_name}** | 📅 التاريخ: **{day:02d}/{month:02d}**.\nالمرجو **اختيار الدولة** من القائمة أدناه لتحديد التوقيت المحلي بدقة:",
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

class TulpaRegisterView(ui.View):
    def __init__(self, bot_instance):
        super().__init__(timeout=None)
        self.bot_instance = bot_instance

    @ui.button(
        label="تسجيل عيد ميلاد تولبا 🌸",
        style=discord.ButtonStyle.secondary,
        custom_id="register_tulpa_birthday_btn"
    )
    async def register_tulpa_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(TulpaBirthdayModal(self.bot_instance))

# ================= 3. سلاش كوماند /setup_birthday (للأعضاء) و /setup_tulpa (للتولبات) =================
@bot.tree.command(name="setup_birthday", description="إرسال رسالة تسجيل أعياد الميلاد للأعضاء 🎂")
async def setup_birthday_slash(interaction: discord.Interaction):
    if not is_owner_or_admin(interaction):
        return await interaction.response.send_message(
            "❌ هذا الأمر مخصص لصاحب البوت أو المشرفين فقط.", ephemeral=True
        )

    embed = discord.Embed(
        title="Birthday Registration 🎂",
        description=(
            "Want Eternal World to 🤍 celebrate your special day?\n\n"
            "اضغط على الزر بالأسفل لتسجيل تاريخ ميلادك!\n\n"
            "Birthday Star 🌟"
        ),
        color=0x2B2D31
    )
    await interaction.response.send_message(embed=embed, view=BirthdayRegisterView(bot), ephemeral=False)

@bot.tree.command(name="setup_tulpa", description="إرسال رسالة تسجيل أعياد ميلاد التولبات 🌸")
async def setup_tulpa_slash(interaction: discord.Interaction):
    if not is_owner_or_admin(interaction):
        return await interaction.response.send_message(
            "❌ هذا الأمر مخصص لصاحب البوت أو المشرفين فقط.", ephemeral=True
        )

    embed = discord.Embed(
        title="Tulpa Birthday Registration 🌸",
        description=(
            "Want Eternal World to 🤍 celebrate your tulpa's special day?\n\n"
            "اضغط على الزر بالأسفل لتسجيل اسم وتاريخ ميلاد تولباك!\n\n"
            "Tulpa Star ✨"
        ),
        color=0x2B2D31
    )
    await interaction.response.send_message(embed=embed, view=TulpaRegisterView(bot), ephemeral=False)

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

    try:
        db = await bot.ensure_db()
        user_id = str(member.id)
        guild_id = str(interaction.guild.id)

        existing = await db.fetchrow(
            """
            SELECT birth_day, birth_month FROM birthdays
            WHERE user_id = $1 AND guild_id = $2 AND COALESCE(entry_type, 'member') = 'member'
            """,
            user_id, guild_id
        )

        if existing:
            return await interaction.response.send_message(
                f"❌ هذا العضو مسجل مسبقاً بالتاريخ ({existing['birth_day']:02d}/{existing['birth_month']:02d}).",
                ephemeral=True
            )

        await db.execute("""
            INSERT INTO birthdays (user_id, guild_id, birth_day, birth_month, timezone, last_wished_year, entry_type, tulpa_name)
            VALUES ($1, $2, $3, $4, 'Africa/Casablanca', 0, 'member', NULL)
        """, user_id, guild_id, day, month)

        await interaction.response.send_message(
            f"✅ تم بنجاح تسجيل تاريخ ميلاد العضو {member.mention} في **{day:02d}/{month:02d}** (بالتوقيت الافتراضي) 🎂",
            ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message("❌ حدث خطأ أثناء الحفظ.", ephemeral=True)
        print("Set birthday DB error:", e)
# ================= 6. سلاش كوماند /change_birthday (للعضو أو التولبا) =================
class ChangeTimezoneSelect(ui.Select):
    def __init__(self, bot_instance, target_type: str, day: int, month: int, tulpa_name: str | None = None):
        self.bot_instance = bot_instance
        self.target_type = target_type
        self.day = day
        self.month = month
        self.tulpa_name = tulpa_name
        super().__init__(
            placeholder="اختر الدولة الجديدة...",
            min_values=1,
            max_values=1,
            options=TIMEZONE_OPTIONS,
        )

    async def callback(self, interaction: discord.Interaction):
        selected_timezone = self.values[0]
        user_id = str(interaction.user.id)
        guild_id = str(interaction.guild.id)

        try:
            db = await self.bot_instance.ensure_db()

            if self.target_type == "tulpa" and self.tulpa_name:
                result = await db.execute("""
                    UPDATE birthdays
                    SET birth_day = $1, birth_month = $2, timezone = $3, last_wished_year = 0
                    WHERE user_id = $4 AND guild_id = $5
                      AND entry_type = 'tulpa'
                      AND LOWER(tulpa_name) = LOWER($6)
                """, self.day, self.month, selected_timezone, user_id, guild_id, self.tulpa_name)

                if result == "UPDATE 0":
                    await db.execute("""
                        INSERT INTO birthdays (user_id, guild_id, birth_day, birth_month, timezone, last_wished_year, entry_type, tulpa_name)
                        VALUES ($1, $2, $3, $4, $5, 0, 'tulpa', $6)
                    """, user_id, guild_id, self.day, self.month, selected_timezone, self.tulpa_name)

                msg = f"✅ تم تحديث عيد ميلاد التولبا **🌸 {self.tulpa_name}** إلى **{self.day:02d}/{self.month:02d}** وتحديد الدولة بنجاح! 🔄"
            else:
                result = await db.execute("""
                    UPDATE birthdays
                    SET birth_day = $1, birth_month = $2, timezone = $3, last_wished_year = 0
                    WHERE user_id = $4 AND guild_id = $5
                      AND COALESCE(entry_type, 'member') = 'member'
                """, self.day, self.month, selected_timezone, user_id, guild_id)

                if result == "UPDATE 0":
                    await db.execute("""
                        INSERT INTO birthdays (user_id, guild_id, birth_day, birth_month, timezone, last_wished_year, entry_type, tulpa_name)
                        VALUES ($1, $2, $3, $4, $5, 0, 'member', NULL)
                    """, user_id, guild_id, self.day, self.month, selected_timezone)

                msg = f"✅ تم تحديث تاريخ ميلادك إلى **{self.day:02d}/{self.month:02d}** وتحديد دولتك بنجاح! 🔄🎂"

            await interaction.response.edit_message(content=msg, view=None)
        except Exception as e:
            await interaction.response.send_message("❌ حدث خطأ أثناء التحديث في قاعدة البيانات.", ephemeral=True)
            print("Change birthday DB error:", e)

class ChangeTimezoneView(ui.View):
    def __init__(self, bot_instance, target_type: str, day: int, month: int, tulpa_name: str | None = None):
        super().__init__(timeout=60)
        self.add_item(ChangeTimezoneSelect(bot_instance, target_type, day, month, tulpa_name))

class ChangeTulpaNameModal(ui.Modal, title="تعديل عيد ميلاد تولبا 🌸"):
    def __init__(self, bot_instance, day: int, month: int):
        super().__init__()
        self.bot_instance = bot_instance
        self.day = day
        self.month = month

    tulpa_name_input = ui.TextInput(
        label="اسم التولبا (Tulpa Name)",
        placeholder="اكتب اسم التولبا...",
        min_length=1,
        max_length=50,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        tulpa_name = self.tulpa_name_input.value.strip()
        if not tulpa_name:
            return await interaction.response.send_message("❌ يرجى إدخال اسم صحيح للتولبا.", ephemeral=True)

        view = ChangeTimezoneView(self.bot_instance, "tulpa", self.day, self.month, tulpa_name)
        await interaction.response.send_message(
            f"🌸 التولبا: **{tulpa_name}** | 📅 التاريخ الجديد: **{self.day:02d}/{self.month:02d}**.\nالمرجو **اختيار الدولة الجديدة** من القائمة أدناه:",
            view=view,
            ephemeral=True
        )

class ChangeTargetSelect(ui.Select):
    def __init__(self, bot_instance, day: int, month: int):
        self.bot_instance = bot_instance
        self.day = day
        self.month = month
        options = [
            discord.SelectOption(label="عيد ميلادي أنا (العضو)", value="member", emoji="🎂"),
            discord.SelectOption(label="عيد ميلاد تولبا 🌸", value="tulpa", emoji="🌸"),
        ]
        super().__init__(placeholder="ماذا تريد أن تعدّل؟", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        choice = self.values[0]
        if choice == "tulpa":
            await interaction.response.send_modal(ChangeTulpaNameModal(self.bot_instance, self.day, self.month))
        else:
            view = ChangeTimezoneView(self.bot_instance, "member", self.day, self.month, None)
            await interaction.response.edit_message(
                content=f"📅 التاريخ الجديد المُدخل لك: **{self.day:02d}/{self.month:02d}**.\nالمرجو **اختيار دولتك الجديدة** من القائمة أدناه:",
                view=view
            )

class ChangeTargetView(ui.View):
    def __init__(self, bot_instance, day: int, month: int):
        super().__init__(timeout=60)
        self.add_item(ChangeTargetSelect(bot_instance, day, month))

@bot.tree.command(name="change_birthday", description="تعديل تاريخ ميلادك أو تاريخ ميلاد تولباك ودولته 🔄")
@app_commands.describe(
    day="اليوم الجديد",
    month="الشهر الجديد"
)
async def change_birthday_command(interaction: discord.Interaction, day: int, month: int):
    if not is_valid_date(day, month):
        return await interaction.response.send_message("❌ هذا التاريخ غير صحيح! يرجى التأكد.", ephemeral=True)

    view = ChangeTargetView(bot, day, month)
    await interaction.response.send_message(
        f"📅 التاريخ الجديد المُدخل: **{day:02d}/{month:02d}**.\nاختر هل تريد تعديل تاريخ ميلادك أم تاريخ ميلاد تولبا:",
        view=view,
        ephemeral=True
    )

# ================= 7. سلاش كوماند /birthday_list (خاص بـ OWNER_ID فقط) =================
@bot.tree.command(name="birthday_list", description="عرض لائحة جميع الأعضاء والتولبات المسجلين في أعياد الميلاد 📋")
async def birthday_list_command(interaction: discord.Interaction):
    if OWNER_ID == 0 or interaction.user.id != OWNER_ID:
        return await interaction.response.send_message("❌ هذا الأمر مخصص لصاحب البوت فقط.", ephemeral=True)

    try:
        db = await bot.ensure_db()
        guild_id = str(interaction.guild.id)

        rows = await db.fetch(
            """
            SELECT user_id, birth_day, birth_month, timezone, entry_type, tulpa_name
            FROM birthdays
            WHERE guild_id = $1
            ORDER BY birth_month, birth_day
            """,
            guild_id
        )

        if not rows:
            return await interaction.response.send_message("📭 لا يوجد أي عضو أو تولبا مسجل في قاعدة بيانات أعياد الميلاد حتى الآن.", ephemeral=True)

        description_lines = []
        for row in rows:
            user_id = str(row["user_id"])
            day = int(row["birth_day"])
            month = int(row["birth_month"])
            tz = row["timezone"] or "Africa/Casablanca"
            entry_type = row["entry_type"] or "member"
            tulpa_name = row["tulpa_name"]

            member = interaction.guild.get_member(int(user_id))
            owner_label = member.mention if member else f"مستخدم مغادر (`{user_id}`)"

            if entry_type == "tulpa" and tulpa_name:
                description_lines.append(
                    f"🌸 تولبا **{tulpa_name}** (رفيق/رفيقة {owner_label}) ⟵ **{day:02d}/{month:02d}** (`{tz}`)"
                )
            else:
                description_lines.append(
                    f"🎂 {owner_label} ⟵ **{day:02d}/{month:02d}** (`{tz}`)"
                )

        embed = discord.Embed(
            title="📋 لائحة أعياد ميلاد أعضاء وتولبات Eternal World",
            description="\n".join(description_lines),
            color=0xFFC0CB
        )
        embed.set_footer(text=f"إجمالي المسجلين: {len(rows)}")

        await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.response.send_message("❌ حدث خطأ أثناء جلب اللائحة من قاعدة البيانات.", ephemeral=True)
        print("Birthday list DB error:", e)

# ================= 8. الفحص الأوتوماتيكي (على جميع السيرفرات + لوقز واضحة) =================
LAST_HEARTBEAT_TS = 0.0

def resolve_channel_for_guild(guild: discord.Guild):
    if TARGET_CHANNEL_ID:
        ch = guild.get_channel(TARGET_CHANNEL_ID)
        if ch:
            return ch
    if CHANNEL_ID:
        ch = guild.get_channel(CHANNEL_ID)
        if ch:
            return ch
    return None

async def send_birthday_announcement(channel: discord.abc.Messageable, member: discord.Member, entry_type: str, tulpa_name: str | None):
    mentions_policy = discord.AllowedMentions(everyone=True, users=True)

    if entry_type == "tulpa" and tulpa_name:
        content_mentions = f"˚₊· ͟͟͞͞➳❥ @everyone ┆ ˚₊· ͟͟͞͞➳❥ 🌸 **✧ {tulpa_name} ✧** ╰┈➤ 🤍 {member.mention}"
        embed = discord.Embed(
            description=build_tulpa_birthday_text(tulpa_name, member.mention),
            color=0xFFC0CB
        )
    else:
        content_mentions = f"@everyone | {member.mention}"
        embed = discord.Embed(
            description=MEMBER_BIRTHDAY_TEXT,
            color=0xFFC0CB
        )

    if os.path.exists(IMAGE_FILENAME):
        file = discord.File(IMAGE_FILENAME, filename="happy_birthday.jpg")
        embed.set_image(url="attachment://happy_birthday.jpg")
        await channel.send(content=content_mentions, embed=embed, file=file, allowed_mentions=mentions_policy)
    else:
        print(f"⚠️ [LOOP-IMG] {IMAGE_FILENAME} not found, sending without image")
        await channel.send(content=content_mentions, embed=embed, allowed_mentions=mentions_policy)

@tasks.loop(minutes=1)
async def check_birthdays():
    global LAST_HEARTBEAT_TS

    try:
        db = await bot.ensure_db()
        now_ts = time.time()
        should_log_heartbeat = (now_ts - LAST_HEARTBEAT_TS) >= 900
        if should_log_heartbeat:
            LAST_HEARTBEAT_TS = now_ts
            print(f"💓 [LOOP-ALIVE] guilds={[f'{g.name}({g.id})' for g in bot.guilds]}")

        for guild in bot.guilds:
            guild_id = str(guild.id)
            channel = resolve_channel_for_guild(guild)

            rows = await db.fetch(
                """
                SELECT ctid, user_id, birth_day, birth_month, timezone, last_wished_year, entry_type, tulpa_name
                FROM birthdays
                WHERE guild_id = $1
                """,
                guild_id
            )

            if should_log_heartbeat:
                ch_info = f"#{channel.id} ({channel.name})" if channel else "NONE"
                print(f"📊 [LOOP-GUILD] guild={guild.name}({guild_id}) | channel={ch_info} | rows={len(rows)}")

            for row in rows:
                row_ctid = row["ctid"]
                user_id = str(row["user_id"])
                day = int(row["birth_day"])
                month = int(row["birth_month"])
                tz_name = row["timezone"] or "Africa/Casablanca"
                last_wished_year = row["last_wished_year"] or 0
                entry_type = row["entry_type"] or "member"
                tulpa_name = row["tulpa_name"]

                try:
                    user_tz = pytz.timezone(tz_name)
                except pytz.UnknownTimeZoneError:
                    print(f"⚠️ [LOOP-TZ] Unknown tz '{tz_name}' for user={user_id} in guild={guild_id}, fallback Africa/Casablanca")
                    user_tz = pytz.timezone("Africa/Casablanca")

                now_user = datetime.now(user_tz)

                is_midnight_window = (now_user.hour == 0)
                is_today = (day == now_user.day and month == now_user.month)

                if is_today and should_log_heartbeat:
                    print(
                        f"🎂 [LOOP-TODAY] guild={guild_id} user={user_id} type={entry_type} tulpa={tulpa_name} "
                        f"tz={tz_name} now={now_user.strftime('%Y-%m-%d %H:%M')} hour==0:{is_midnight_window} "
                        f"last_wished_year:{last_wished_year} cur_year:{now_user.year}"
                    )

                if is_midnight_window and is_today and last_wished_year != now_user.year:
                    if not channel:
                        print(f"❌ [LOOP-NO-CH] No valid channel resolved for guild={guild.name}({guild_id}) to wish user={user_id}")
                        continue

                    print(f"🚀 [LOOP-SENDING] guild={guild_id} user={user_id} type={entry_type} tulpa={tulpa_name} -> #{channel.id}")

                    member = guild.get_member(int(user_id))
                    if not member:
                        try:
                            member = await guild.fetch_member(int(user_id))
                        except Exception as e:
                            print(f"❌ [LOOP-MEMBER-ERR] fetch_member failed user={user_id} guild={guild_id}: {e}")
                            member = None

                    if not member:
                        print(f"⚠️ [LOOP-SKIP] Member {user_id} not in guild {guild_id}")
                        continue

                    try:
                        await send_birthday_announcement(channel, member, entry_type, tulpa_name)
                    except Exception as send_err:
                        print(f"❌ [LOOP-SEND-ERR] guild={guild_id} ch=#{channel.id} user={user_id}: {send_err}")
                        continue

                    await db.execute(
                        "UPDATE birthdays SET last_wished_year = $1 WHERE ctid = $2",
                        now_user.year, row_ctid
                    )
                    print(f"✅ [LOOP-SENT] guild={guild_id} user={user_id} type={entry_type} year={now_user.year}")

    except Exception as e:
        print(f"❌ [LOOP-CRASH] check_birthdays error: {repr(e)}")

@check_birthdays.before_loop
async def before_check():
    await bot.wait_until_ready()
    print("⏳ [LOOP-READY] check_birthdays started after bot ready.")

# ================= 9. إرسال تهنئة فورية في روم محدد (للأونر فقط) =================
@bot.tree.command(name="send_birthday_now", description="إرسال تهنئة عيد الميلاد الكاملة فوراً في الروم المحدد (للأونر فقط) 🎂🌸")
@app_commands.describe(
    member="العضوة اللي بغيتي تهنّيها دابا",
    tulpa_name="اختياري: اكتب اسم التولبا إلا بغيتي ترسل تهنئة تولبا"
)
async def send_birthday_now_command(interaction: discord.Interaction, member: discord.Member, tulpa_name: str | None = None):
    if OWNER_ID == 0 or interaction.user.id != OWNER_ID:
        return await interaction.response.send_message("❌ هذا الأمر مخصص لصاحب البوت فقط.", ephemeral=True)

    channel = bot.get_channel(TARGET_CHANNEL_ID) if TARGET_CHANNEL_ID else None
    if not channel:
        return await interaction.response.send_message("❌ تأكدي من وضع `TARGET_CHANNEL_ID` صحيح أو أن البوت يقدر يشوف هاد الروم.", ephemeral=True)

    cleaned_tulpa = tulpa_name.strip() if tulpa_name and tulpa_name.strip() else None
    entry_type = "tulpa" if cleaned_tulpa else "member"

    confirm_msg = (
        f"✅ تم إرسال تهنئة التولبا **🌸 {cleaned_tulpa}** (العضو {member.mention}) في {channel.mention}."
        if cleaned_tulpa
        else f"✅ تم إرسال التهنئة لـ {member.mention} في {channel.mention}."
    )
    await interaction.response.send_message(confirm_msg, ephemeral=True)
    await send_birthday_announcement(channel, member, entry_type, cleaned_tulpa)

@bot.event
async def on_ready():
    print(f"✅ البوت يعمل الآن باسم: {bot.user}")
    if not check_birthdays.is_running():
        check_birthdays.start()

bot.run(TOKEN)
                 
