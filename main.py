import discord
from discord.ext import commands
import asyncio
import json
import os
from datetime import datetime
from pathlib import Path


# --- НАСТРОЙКИ ---
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("Переменная окружения DISCORD_TOKEN не задана!")

CHANNEL_ID = int(os.getenv("CHANNEL_ID", "1197494268353314882"))
REMINDER_HOURS = int(os.getenv("REMINDER_HOURS", "3"))
LOG_CHANNEL_ID = None

DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
# -----------------

LOG_FILE   = DATA_DIR / "clicks.json"
STATE_FILE = DATA_DIR / "state.json"
EXCEL_FILE = DATA_DIR / "Logs.xlsx"
SHEET_NAME = "Logs"

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

current_message_id = None
reminder_task = None
clicks_log = []

# Глобальное состояние
is_fed = False
is_milked = False


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


# ---------- ЭКСПОРТ В EXCEL ----------
def export_to_excel(entries: list) -> str:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    wb = Workbook()
    ws = wb.active
    ws.title = SHEET_NAME

    headers = ["#", "Время", "Пользователь", "ID", "Действие"]
    ws.append(headers)

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="4F81BD")
    thin = Side(style="thin", color="000000")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    center = Alignment(horizontal="center", vertical="center")

    for col, _ in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center
        cell.border = border

    for i, e in enumerate(entries, start=1):
        ws.append([i, e["time"], e["display_name"], e["user_id"], e["action"]])

    for row in ws.iter_rows(min_row=2, max_row=ws.max_row, max_col=len(headers)):
        for cell in row:
            cell.border = border
            cell.alignment = Alignment(horizontal="left", vertical="center")

    widths = [6, 22, 24, 20, 12]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = w

    wb.save(EXCEL_FILE)
    return EXCEL_FILE


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
        
        await self.update_buttons(interaction)
        await reset_timer()

    async def update_buttons(self, interaction: discord.Interaction):
        global is_fed, is_milked
        
        # Меняем текст на кнопках в ТЕКУЩЕМ сообщении (делаем зелеными)
        self.btn_feed.label = f"{'🟢' if is_fed else '🔴'} покормил"
        self.btn_milk.label = f"{'🟢' if is_milked else '🔴'} подоил"
        await interaction.message.edit(view=self)

        # Если нажаты ОБЕ кнопки
        if is_fed and is_milked:
            # СБРАСЫВАЕМ состояние для СЛЕДУЮЩЕГО сообщения, 
            # но НЕ трогаем кнопки в текущем (они останутся зелеными)
            is_fed = False
            is_milked = False
            save_state()
# ---------- ТАЙМЕР НА 3 ЧАСА ----------
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
    global current_message_id
    # При отправке нового сообщения читаем актуальное состояние из файла
    load_state()
    
    channel = bot.get_channel(CHANNEL_ID)
    if channel is None:
        channel = discord.utils.get(bot.get_all_channels(), id=CHANNEL_ID)
        
    if channel is None:
        print(f"❌ ОШИБКА: Канал с ID {CHANNEL_ID} не найден!")
        return
        
    view = FarmView()
    msg = await channel.send("Нажмите кнопку, когда выполните действие:", view=view)
    current_message_id = msg.id
    print(f"✅ Сообщение отправлено (ID: {current_message_id}) в канал {channel.name}")


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
    """Принудительно выводит кнопки (состояние сохраняется)."""
    await send_farm_message()
    await ctx.message.delete()

@bot.command(name="log")
@commands.has_permissions(administrator=True)
async def show_log(ctx: commands.Context, limit: int = 10):
    if not clicks_log:
        await ctx.send(f"Лист **{SHEET_NAME}** пуст.")
        return
    recent = clicks_log[-limit:]
    loop = asyncio.get_event_loop()
    try:
        path = await loop.run_in_executor(None, export_to_excel, recent)
    except ImportError:
        await ctx.send("❌ Не установлен модуль `openpyxl`. Установите: `pip install openpyxl`")
        return
    await ctx.send(f"📊 Лист **{SHEET_NAME}** — последние {len(recent)} записей:", file=discord.File(path))


@bot.command(name="clearlog")
@commands.has_permissions(administrator=True)
async def clear_log(ctx: commands.Context):
    clicks_log.clear()
    save_log()
    await ctx.send(f"Лист **{SHEET_NAME}** очищен.")


@bot.command(name="logcount")
@commands.has_permissions(administrator=True)
async def log_count(ctx: commands.Context):
    await ctx.send(f"Всего записей в листе **{SHEET_NAME}**: **{len(clicks_log)}**")


bot.run(TOKEN)
