#!/usr/bin/env python3
"""
Dragon Pet — добрый бот-дракон для Lolka
Позволяет каждому пользователю завести своего личного дракона.
Стихии • Ежедневные награды • Таблица лидеров • Красивые эмодзи-аватары
"""

import os
import random
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
import aiosqlite
from datetime import datetime, timezone, timedelta

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
DB_PATH = "dragons.db"

# ─── Настройки ───────────────────────────────────────────────────────────────
MAX_HUNGER = 100
MAX_MOOD = 100
FEED_AMOUNT = 25
PLAY_AMOUNT = 20
HUNGER_DECAY_HOURS = 6
MOOD_DECAY_HOURS = 8

# ─── Стихии ───────────────────────────────────────────────────────────────────
ELEMENTS = {
    "огонь":  {"emoji": "🔥", "color": 0xE74C3C, "name": "Огонь",  "bonus": "Сила пламени"},
    "вода":   {"emoji": "💧", "color": 0x3498DB, "name": "Вода",   "bonus": "Глубокие воды"},
    "земля":  {"emoji": "🌍", "color": 0x27AE60, "name": "Земля",  "bonus": "Каменная броня"},
    "воздух": {"emoji": "🌪️", "color": 0x95A5A6, "name": "Воздух", "bonus": "Быстрый полёт"},
    "тень":   {"emoji": "🌑", "color": 0x2C3E50, "name": "Тень",   "bonus": "Скрытность"},
    "свет":   {"emoji": "✨", "color": 0xF1C40F, "name": "Свет",   "bonus": "Сияние"},
}

# ─── Эмодзи-аватары по уровню и стихии ───────────────────────────────────────
def get_dragon_avatar(element: str, level: int) -> str:
    """Возвращает красивый эмодзи-аватар в зависимости от стихии и уровня."""
    stage = "baby" if level < 5 else "young" if level < 15 else "adult" if level < 30 else "ancient"

    avatars = {
        "огонь":  {"baby": "🐣🔥", "young": "🐲🔥", "adult": "🐉🔥", "ancient": "🔥🐉🔥"},
        "вода":   {"baby": "🐣💧", "young": "🐲💧", "adult": "🐉💧", "ancient": "💧🐉💧"},
        "земля":  {"baby": "🐣🌍", "young": "🐲🌍", "adult": "🐉🌍", "ancient": "🌍🐉🌍"},
        "воздух": {"baby": "🐣🌪️", "young": "🐲🌪️", "adult": "🐉🌪️", "ancient": "🌪️🐉🌪️"},
        "тень":   {"baby": "🐣🌑", "young": "🐲🌑", "adult": "🐉🌑", "ancient": "🌑🐉🌑"},
        "свет":   {"baby": "🐣✨", "young": "🐲✨", "adult": "🐉✨", "ancient": "✨🐉✨"},
    }
    return avatars.get(element, avatars["огонь"]).get(stage, "🐉")


intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


# ─── База данных ──────────────────────────────────────────────────────────────
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS dragons (
                user_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                element TEXT DEFAULT 'огонь',
                level INTEGER DEFAULT 1,
                exp INTEGER DEFAULT 0,
                hunger INTEGER DEFAULT 50,
                mood INTEGER DEFAULT 70,
                created_at TEXT NOT NULL,
                last_feed TEXT,
                last_play TEXT,
                last_daily TEXT
            )
        """)
        # Миграция на случай старой базы
        try:
            await db.execute("ALTER TABLE dragons ADD COLUMN element TEXT DEFAULT 'огонь'")
        except Exception:
            pass
        try:
            await db.execute("ALTER TABLE dragons ADD COLUMN last_daily TEXT")
        except Exception:
            pass
        await db.commit()


def calculate_level(exp: int) -> int:
    return max(1, exp // 100 + 1)


def exp_for_next_level(level: int) -> int:
    return level * 100


async def get_dragon(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM dragons WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def update_dragon(user_id: int, **kwargs):
    if not kwargs:
        return
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [user_id]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE dragons SET {sets} WHERE user_id = ?", values)
        await db.commit()


async def apply_decay(dragon: dict) -> dict:
    """Применяет естественный голод и спад настроения."""
    now = datetime.now(timezone.utc)
    updated = False

    last_feed = dragon.get("last_feed")
    if last_feed:
        last = datetime.fromisoformat(last_feed)
        hours = (now - last).total_seconds() / 3600
        decay = int(hours // HUNGER_DECAY_HOURS) * 15
        if decay > 0:
            dragon["hunger"] = max(0, dragon["hunger"] - decay)
            updated = True

    last_play = dragon.get("last_play")
    if last_play:
        last = datetime.fromisoformat(last_play)
        hours = (now - last).total_seconds() / 3600
        decay = int(hours // MOOD_DECAY_HOURS) * 10
        if decay > 0:
            dragon["mood"] = max(0, dragon["mood"] - decay)
            updated = True

    if updated:
        await update_dragon(
            dragon["user_id"],
            hunger=dragon["hunger"],
            mood=dragon["mood"]
        )
    return dragon


def make_embed(dragon: dict, title: str = None) -> discord.Embed:
    level = calculate_level(dragon["exp"])
    next_exp = exp_for_next_level(level)
    element = dragon.get("element", "огонь")
    elem_data = ELEMENTS.get(element, ELEMENTS["огонь"])
    avatar = get_dragon_avatar(element, level)

    hunger_bar = "🟩" * (dragon["hunger"] // 10) + "⬛" * (10 - dragon["hunger"] // 10)
    mood_bar = "💖" * (dragon["mood"] // 10) + "🖤" * (10 - dragon["mood"] // 10)

    # Цвет от стихии, но предупреждающий если плохое состояние
    color = elem_data["color"]
    if dragon["hunger"] < 15 or dragon["mood"] < 15:
        color = 0xED4245
    elif dragon["hunger"] < 30 or dragon["mood"] < 30:
        color = 0xFEE75C

    embed = discord.Embed(
        title=title or f"{avatar} {dragon['name']}",
        color=color,
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(
        name="Стихия",
        value=f"{elem_data['emoji']} **{elem_data['name']}**\n*{elem_data['bonus']}*",
        inline=True
    )
    embed.add_field(
        name="Уровень",
        value=f"**{level}**\nопыт {dragon['exp']}/{next_exp}",
        inline=True
    )
    embed.add_field(name="\u200b", value="\u200b", inline=True)  # пустое поле для выравнивания

    embed.add_field(name="Голод", value=f"{hunger_bar}\n{dragon['hunger']}/100", inline=False)
    embed.add_field(name="Настроение", value=f"{mood_bar}\n{dragon['mood']}/100", inline=False)

    status = []
    if dragon["hunger"] < 20:
        status.append("Хочет кушать...")
    if dragon["mood"] < 20:
        status.append("Скучает по тебе...")
    if not status:
        status.append("Доволен и счастлив!")

    embed.set_footer(text=f"{avatar}  " + " • ".join(status))
    return embed


# ─── События ─────────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    await init_db()
    try:
        synced = await bot.tree.sync()
        print(f"Синхронизировано {len(synced)} команд")
    except Exception as e:
        print(f"Ошибка синхронизации: {e}")
    print(f"🐉 Dragon Pet готов! Вошёл как {bot.user}")


# ─── Основная команда /dragon ─────────────────────────────────────────────────
@bot.tree.command(name="dragon", description="Управление своим драконом")
@app_commands.describe(
    action="Что сделать",
    name="Имя дракона (для create и rename)",
    element="Стихия дракона (только при create)"
)
@app_commands.choices(action=[
    app_commands.Choice(name="create — завести дракона", value="create"),
    app_commands.Choice(name="info — статус дракона", value="info"),
    app_commands.Choice(name="feed — покормить", value="feed"),
    app_commands.Choice(name="play — поиграть", value="play"),
    app_commands.Choice(name="daily — ежедневная награда", value="daily"),
    app_commands.Choice(name="top — таблица лидеров", value="top"),
    app_commands.Choice(name="rename — переименовать", value="rename"),
    app_commands.Choice(name="release — отпустить", value="release"),
])
@app_commands.choices(element=[
    app_commands.Choice(name="🔥 Огонь", value="огонь"),
    app_commands.Choice(name="💧 Вода", value="вода"),
    app_commands.Choice(name="🌍 Земля", value="земля"),
    app_commands.Choice(name="🌪️ Воздух", value="воздух"),
    app_commands.Choice(name="🌑 Тень", value="тень"),
    app_commands.Choice(name="✨ Свет", value="свет"),
])
async def dragon_command(
    interaction: discord.Interaction,
    action: str,
    name: str = None,
    element: str = None
):
    user_id = interaction.user.id
    dragon = await get_dragon(user_id)

    # ── CREATE ───────────────────────────────────────────────────────────────
    if action == "create":
        if dragon:
            await interaction.response.send_message(
                f"У тебя уже есть дракон **{dragon['name']}**! Используй `/dragon info`.",
                ephemeral=True
            )
            return
        if not name or len(name) < 2 or len(name) > 20:
            await interaction.response.send_message(
                "Пожалуйста, укажи имя дракона от 2 до 20 символов.\n"
                "Пример: `/dragon create Огонёк element:Огонь`",
                ephemeral=True
            )
            return

        # Если стихию не выбрали — случайная
        if not element:
            element = random.choice(list(ELEMENTS.keys()))

        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """INSERT INTO dragons
                   (user_id, name, element, created_at, last_feed, last_play)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (user_id, name, element, now, now, now)
            )
            await db.commit()

        elem_data = ELEMENTS[element]
        avatar = get_dragon_avatar(element, 1)

        embed = discord.Embed(
            title=f"{avatar} Новый дракон появился!",
            description=(
                f"**{name}** теперь твой верный спутник!\n\n"
                f"Стихия: {elem_data['emoji']} **{elem_data['name']}**\n"
                f"*{elem_data['bonus']}*\n\n"
                f"Корми его, играй и растите вместе."
            ),
            color=elem_data["color"]
        )
        embed.set_footer(text="Используй /dragon info чтобы посмотреть статус")
        await interaction.response.send_message(embed=embed)
        return

    # ── TOP (таблица лидеров) — доступна всем ────────────────────────────────
    if action == "top":
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT user_id, name, element, exp FROM dragons ORDER BY exp DESC LIMIT 10"
            ) as cursor:
                rows = await cursor.fetchall()

        if not rows:
            await interaction.response.send_message("Пока нет ни одного дракона... Будь первым!")
            return

        embed = discord.Embed(
            title="🏆 Таблица лидеров — Топ-10 драконов",
            color=0xF1C40F,
            timestamp=datetime.now(timezone.utc)
        )

        medals = ["🥇", "🥈", "🥉"] + ["🔹"] * 7
        lines = []
        for i, row in enumerate(rows):
            level = calculate_level(row["exp"])
            elem = row["element"] or "огонь"
            avatar = get_dragon_avatar(elem, level)
            medal = medals[i]
            lines.append(
                f"{medal} **{row['name']}** {avatar}\n"
                f"  Ур. {level} • {ELEMENTS.get(elem, ELEMENTS['огонь'])['emoji']} {ELEMENTS.get(elem, ELEMENTS['огонь'])['name']} • {row['exp']} опыта"
            )

        embed.description = "\n\n".join(lines)
        embed.set_footer(text="Расти своего дракона и займи место на вершине!")
        await interaction.response.send_message(embed=embed)
        return

    # Дальше нужны наличие дракона
    if not dragon:
        await interaction.response.send_message(
            "У тебя ещё нет дракона! Заведи его командой:\n`/dragon create <имя>`",
            ephemeral=True
        )
        return

    # Применяем спад
    dragon = await apply_decay(dragon)
    element = dragon.get("element", "огонь")
    elem_data = ELEMENTS.get(element, ELEMENTS["огонь"])

    # ── INFO ─────────────────────────────────────────────────────────────────
    if action == "info":
        embed = make_embed(dragon)
        await interaction.response.send_message(embed=embed)
        return

    # ── FEED ─────────────────────────────────────────────────────────────────
    if action == "feed":
        if dragon["hunger"] >= 95:
            await interaction.response.send_message(
                f"**{dragon['name']}** уже сыт и отказывается есть!",
                ephemeral=True
            )
            return

        new_hunger = min(MAX_HUNGER, dragon["hunger"] + FEED_AMOUNT)
        new_exp = dragon["exp"] + random.randint(5, 12)
        now = datetime.now(timezone.utc).isoformat()

        await update_dragon(user_id, hunger=new_hunger, exp=new_exp, last_feed=now)
        dragon["hunger"] = new_hunger
        dragon["exp"] = new_exp

        phrases = [
            f"**{dragon['name']}** с удовольствием слопал угощение!",
            f"**{dragon['name']}** довольно урчит и ест.",
            f"Ням-ням! **{dragon['name']}** очень доволен.",
        ]
        embed = make_embed(dragon, title=random.choice(phrases))
        await interaction.response.send_message(embed=embed)
        return

    # ── PLAY ─────────────────────────────────────────────────────────────────
    if action == "play":
        if dragon["mood"] >= 95:
            await interaction.response.send_message(
                f"**{dragon['name']}** уже полон энергии и счастлив!",
                ephemeral=True
            )
            return

        new_mood = min(MAX_MOOD, dragon["mood"] + PLAY_AMOUNT)
        new_exp = dragon["exp"] + random.randint(8, 15)
        new_hunger = max(0, dragon["hunger"] - 5)
        now = datetime.now(timezone.utc).isoformat()

        await update_dragon(user_id, mood=new_mood, exp=new_exp, hunger=new_hunger, last_play=now)
        dragon["mood"] = new_mood
        dragon["exp"] = new_exp
        dragon["hunger"] = new_hunger

        phrases = [
            f"Ты поиграл с **{dragon['name']}**! Он счастлив.",
            f"**{dragon['name']}** весело носится вокруг тебя.",
            f"Игра окончена. **{dragon['name']}** довольно фыркает.",
        ]
        embed = make_embed(dragon, title=random.choice(phrases))
        await interaction.response.send_message(embed=embed)
        return

    # ── DAILY ────────────────────────────────────────────────────────────────
    if action == "daily":
        now = datetime.now(timezone.utc)
        last_daily = dragon.get("last_daily")

        if last_daily:
            last = datetime.fromisoformat(last_daily)
            if (now - last) < timedelta(hours=20):  # чуть меньше суток, чтобы было удобно
                remaining = timedelta(hours=20) - (now - last)
                hours = int(remaining.total_seconds() // 3600)
                minutes = int((remaining.total_seconds() % 3600) // 60)
                await interaction.response.send_message(
                    f"Ежедневная награда уже получена!\n"
                    f"Приходи через **{hours}ч {minutes}м**.",
                    ephemeral=True
                )
                return

        # Награда
        exp_gain = random.randint(30, 60)
        hunger_gain = random.randint(15, 30)
        mood_gain = random.randint(15, 30)

        new_exp = dragon["exp"] + exp_gain
        new_hunger = min(MAX_HUNGER, dragon["hunger"] + hunger_gain)
        new_mood = min(MAX_MOOD, dragon["mood"] + mood_gain)

        await update_dragon(
            user_id,
            exp=new_exp,
            hunger=new_hunger,
            mood=new_mood,
            last_daily=now.isoformat()
        )
        dragon["exp"] = new_exp
        dragon["hunger"] = new_hunger
        dragon["mood"] = new_mood

        avatar = get_dragon_avatar(element, calculate_level(new_exp))
        embed = discord.Embed(
            title=f"{avatar} Ежедневная награда!",
            description=(
                f"**{dragon['name']}** получил подарки:\n\n"
                f"✨ **+{exp_gain}** опыта\n"
                f"🍖 **+{hunger_gain}** сытости\n"
                f"💖 **+{mood_gain}** настроения"
            ),
            color=elem_data["color"]
        )
        embed = make_embed(dragon, title=f"{avatar} Ежедневная награда получена!")
        await interaction.response.send_message(embed=embed)
        return

    # ── RENAME ───────────────────────────────────────────────────────────────
    if action == "rename":
        if not name or len(name) < 2 or len(name) > 20:
            await interaction.response.send_message(
                "Укажи новое имя от 2 до 20 символов.",
                ephemeral=True
            )
            return
        old_name = dragon["name"]
        await update_dragon(user_id, name=name)
        await interaction.response.send_message(
            f"Дракон **{old_name}** теперь называется **{name}**! ✨"
        )
        return

    # ── RELEASE ──────────────────────────────────────────────────────────────
    if action == "release":
        await interaction.response.send_message(
            f"Ты уверен, что хочешь отпустить **{dragon['name']}**?\n"
            f"Это действие необратимо.\n\n"
            f"Чтобы подтвердить — напиши в чат: `отпустить {dragon['name']}`",
            ephemeral=True
        )
        return


# ─── Подтверждение отпускания ─────────────────────────────────────────────────
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    content = message.content.lower().strip()
    if content.startswith("отпустить "):
        name = content[10:].strip()
        dragon = await get_dragon(message.author.id)
        if dragon and dragon["name"].lower() == name:
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("DELETE FROM dragons WHERE user_id = ?", (message.author.id,))
                await db.commit()
            await message.channel.send(
                f"**{dragon['name']}** улетел в небо... Прощай, маленький друг. 🕊️"
            )
        else:
            await message.channel.send("У тебя нет дракона с таким именем.", delete_after=10)

    await bot.process_commands(message)


if __name__ == "__main__":
    if not TOKEN:
        print("Ошибка: не указан BOT_TOKEN в .env")
    else:
        bot.run(TOKEN)
