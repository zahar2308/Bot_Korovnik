import discord
from discord.ext import commands
import asyncio
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- НАСТРОЙКИ ---
TOKEN = os.getenv("DISCORD_TOKEN", "ВАШ_ТОКЕН_ЗДЕСЬ")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "1197494268353314882"))
REMINDER_HOURS = int(os.getenv("REMINDER_HOURS", "3"))

# Настройки Google
GOOGLE_CREDENTIALS_FILE = "credentials.json" 
GOOGLE_SHEET_ID = "1EXeD14wIJtXLGgLN1E47tW2HIhwrpzmym9aZuQPPXAw" 
GOOGLE_SHEET_NAME = "Коровник" 
# -----------------

DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

LOG_FILE   = DATA_DIR / "clicks.json"
STATE_FILE = DATA_DIR / "state.json"

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

clicks_log = []
is_fed = False
is_milked = False


# ---------- РАБОТА С GOOGLE SHEETS ----------
def upload_to_google_sheets(entries: list) -> str:
    """Отправляет данные в Google Таблицу и возвращает ссылку на неё."""
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDENTIALS_FILE, scope)
    client = gspread.authorize(creds)
    
    sheet = client.open_by_key(GOOGLE_SHEET_ID)
    
    try:
        worksheet = sheet.worksheet(GOOGLE_SHEET_NAME)
    except gspread.exceptions.WorksheetNotFound:
        worksheet = sheet.add_worksheet(title=GOOGLE_SHEET_NAME, rows="100", cols="5")

    worksheet.clear()

    headers = ["#", "Время", "Пользователь", "ID", "Действие"]
    data = [headers]
    
    for i, e in enumerate(entries, start=1):
        data.append([str(i), e["time"], e["display_name"], str(e["user_id"]), e["action"]])

    worksheet.update(values=data, range_name="A1")
    
    worksheet.format("A1:E1", {
        "textFormat": {"bold": True},
        "backgroundColor": {"red": 0.3, "green": 0.5, "blue": 0.7},
        "horizontalAlignment": "CENTER"
    })

    return f"https://docs.google.com/spreadsheets/d/{GOOGLE_SHEET_ID}"


# ---------- СОХРАНЕНИЕ СОСТОЯНИЯ ----------
def save_state():
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"is_fed": is_fed, "is_milked": is_milked}, f)

def load_state():
    global is_fed, is_milked
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            is_fed = data.get("is_fed", False)
            is_milked = data.get("is_milked", False)
    except FileNotFoundError:
        is_fed = False
        is_milked = False


# ---------- РАБОТА С ЛОГОМ ----------
def load_log():
    global clicks_log
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            clicks_log = json.load(f)
        print(f"Загружено {len(clicks_log)} записей из файла.")
    except FileNotFoundError:
        clicks_log = []
        print("Файл лога не найден — начинаем с пустого лога.")

def save_log():
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(clicks_log, f, ensure_ascii=False, indent=2)


# ---------- VIEW С КНОПКАМИ ----------
class FarmView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        
        self.btn_feed = discord.ui.Button(
            label=f"{'🟢' if is_fed else '🔴'} покормил", 
            style=discord.ButtonStyle.green, 
            custom_id="feed_button"
        )
        self.btn_milk = discord.ui.Button(
            label=f"{'🟢' if is_milked else '🔴'} подоил", 
            style=discord.ButtonStyle.blurple, 
            custom_id="milk_button"
        )

        self.btn_feed.callback = self.feed_callback
        self.btn_milk.callback = self.milk_callback
        self.add_item(self.btn_feed)
        self.add_item(self.btn_milk)

    async def feed_callback(self, interaction: discord.Interaction):
        global is_fed
        if is_fed:
            await interaction.response.send_message("Вы уже покормили! Дождитесь второго действия.", ephemeral=True)
            return
            
        is_fed = True
        save_state()
        await self.log_click(interaction, "покормил")
        await interaction.response.send_message("Вы покормили! 🍎", ephemeral=True)

        self.btn_feed.disabled = True
        await self.update_buttons(interaction)
        await reset_timer()

    async def milk_callback(self, interaction: discord.Interaction):
        global is_milked
        if is_milked:
            await interaction.response.send_message("Вы уже подоили! Дождитесь второго действия.", ephemeral=True)
            return

        is_milked = True
        save_state()
        await self.log_click(interaction, "подоил")
        await interaction.response.send_message("Вы подоили! 🥛", ephemeral=True)
        
        self.btn_milk.disabled = True
        await self.update_buttons(interaction)
        await reset_timer()

    async def update_buttons(self, interaction: discord.Interaction):
        global is_fed, is_milked
        
        self.btn_feed.label = f"{'🟢' if is_fed else '🔴'} покормил"
        self.btn_milk.label = f"{'🟢' if is_milked else '🔴'} подоил"
        await interaction.message.edit(view=self)

        if is_fed and is_milked:
            is_fed = False
            is_milked = False
            save_state()

# ---------- ТАЙМЕР ----------
    async def log_click(self, interaction: discord.Interaction, action: str):
        now = datetime.now()
        
        current_hour = now.replace(minute=0, second=0, microsecond=0)
        bucket_time = current_hour + timedelta(hours=3)

        entry = {
            "user_id": interaction.user.id,
            "user_name": str(interaction.user),
            "display_name": interaction.user.display_name,
            "action": action,
            "time": bucket_time.strftime("%Y-%m-%d %H:%M:%S"),
            "channel_id": interaction.channel_id,
        }
        clicks_log.append(entry)
        save_log()
        print(f"[{entry['time']}] {entry['user_name']} (ID: {entry['user_id']}) — {action}")


# ---------- ОТПРАВКА СООБЩЕНИЯ ----------
async def send_farm_message():
    load_state()
    channel = bot.get_channel(CHANNEL_ID)
    if channel is None:
        print(f"❌ ОШИБКА: Канал с ID {CHANNEL_ID} не найден!")
        return
        
    view = FarmView()
    await channel.send("Нажмите кнопку, когда выполните действие:", view=view)

async def reset_timer():
    global reminder_task
    if reminder_task and not reminder_task.done():
        reminder_task.cancel()
    reminder_task = asyncio.create_task(wait_and_send())

async def wait_and_send():
    try:
        await asyncio.sleep(REMINDER_HOURS * 60 * 60)
        await send_farm_message()
    except asyncio.CancelledError:
        pass


# ---------- СОБЫТИЯ ----------
@bot.event
async def on_ready():
    print(f'Бот {bot.user} запущен!')
    load_log()
    bot.add_view(FarmView())
    await send_farm_message()
    await reset_timer()


# ---------- КОМАНДЫ ----------
@bot.command(name="test")
async def test_cmd(ctx: commands.Context):
    await send_farm_message()
    await ctx.message.delete()

@bot.command(name="log")
@commands.has_permissions(administrator=True)
async def show_log(ctx: commands.Context, limit: int = 10):
    if not clicks_log:
        await ctx.send(f"Таблица **{GOOGLE_SHEET_NAME}** пуста.")
        return
        
    recent = clicks_log[-limit:]
    
    loop = asyncio.get_event_loop()
    try:
        url = await loop.run_in_executor(None, upload_to_google_sheets, recent)
    except Exception as e:
        await ctx.send(f"❌ Ошибка при отправке в Google: {e}")
        return

    await ctx.send(f"📊 Логи успешно обновлены! Посмотреть таблицу: {url}")

@bot.command(name="clearlog")
@commands.has_permissions(administrator=True)
async def clear_log(ctx: commands.Context):
    clicks_log.clear()
    save_log()
    await ctx.send(f"Лог очищен.")

bot.run(TOKEN)
