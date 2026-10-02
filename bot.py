#!/usr/bin/env python3
"""
Dragon Pet — добрый бот-дракон для Lolka
Позволяет каждому пользователю завести своего личного дракона.
"""

import os
import random
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
import aiosqlite
from datetime import datetime, timezone

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
DB_PATH = "dragons.db"

# Настройки драконов
MAX_HUNGER = 100
MAX_MOOD = 100
FEED_AMOUNT = 25
PLAY_AMOUNT = 20
HUNGER_DECAY_HOURS = 6   # каждые 6 часов голод растёт
MOOD_DECAY_HOURS = 8

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS dragons (
                user_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                level INTEGER DEFAULT 1,
                exp INTEGER DEFAULT 0,
                hunger INTEGER DEFAULT 50,
                mood INTEGER DEFAULT 70,
                created_at TEXT NOT NULL,
                last_feed TEXT,
                last_play TEXT
            )
        """)
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

    # Голод
    last_feed = dragon.get("last_feed")
    if last_feed:
        last = datetime.fromisoformat(last_feed)
        hours = (now - last).total_seconds() / 3600
        decay = int(hours // HUNGER_DECAY_HOURS) * 15
        if decay > 0:
            dragon["hunger"] = max(0, dragon["hunger"] - decay)
            updated = True

    # Настроение
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
    progress = dragon["exp"] % 100

    hunger_bar = "🟩" * (dragon["hunger"] // 10) + "⬛" * (10 - dragon["hunger"] // 10)
    mood_bar = "💖" * (dragon["mood"] // 10) + "🖤" * (10 - dragon["mood"] // 10)

    color = 0x57F287  # зелёный
    if dragon["hunger"] < 30 or dragon["mood"] < 30:
        color = 0xFEE75C  # жёлтый
    if dragon["hunger"] < 15 or dragon["mood"] < 15:
        color = 0xED4245  # красный

    embed = discord.Embed(
        title=title or f"🐉 {dragon['name']}",
        color=color,
        timestamp=datetime.now(timezone.utc)
    )
    embed.add_field(name="Уровень", value=f"**{level}** (опыт {dragon['exp']}/{next_exp})", inline=True)
    embed.add_field(name="Голод", value=f"{hunger_bar}\n{dragon['hunger']}/100", inline=False)
    embed.add_field(name="Настроение", value=f"{mood_bar}\n{dragon['mood']}/100", inline=False)

    status = []
    if dragon["hunger"] < 20:
        status.append("Хочет кушать...")
    if dragon["mood"] < 20:
        status.append("Скучает по тебе...")
    if not status:
        status.append("Доволен и счастлив!")

    embed.set_footer(text=" • ".join(status))
    return embed


@bot.event
async def on_ready():
    await init_db()
    try:
        synced = await bot.tree.sync()
        print(f"Синхронизировано {len(synced)} команд")
    except Exception as e:
        print(f"Ошибка синхронизации: {e}")
    print(f"🐉 Dragon Pet готов! Вошёл как {bot.user}")


@bot.tree.command(name="dragon", description="Управление своим драконом")
@app_commands.describe(
    action="Что сделать",
    name="Имя дракона (для create и rename)"
)
@app_commands.choices(action=[
    app_commands.Choice(name="create — завести дракона", value="create"),
    app_commands.Choice(name="info — статус дракона", value="info"),
    app_commands.Choice(name="feed — покормить", value="feed"),
    app_commands.Choice(name="play — поиграть", value="play"),
    app_commands.Choice(name="rename — переименовать", value="rename"),
    app_commands.Choice(name="release — отпустить", value="release"),
])
async def dragon_command(interaction: discord.Interaction, action: str, name: str = None):
    user_id = interaction.user.id
    dragon = await get_dragon(user_id)

    if action == "create":
        if dragon:
            await interaction.response.send_message(
                f"У тебя уже есть дракон **{dragon['name']}**! Используй `/dragon info`.",
                ephemeral=True
            )
            return
        if not name or len(name) < 2 or len(name) > 20:
            await interaction.response.send_message(
                "Пожалуйста, укажи имя дракона от 2 до 20 символов.\nПример: `/dragon create Огонёк`",
                ephemeral=True
            )
            return

        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO dragons (user_id, name, created_at, last_feed, last_play) VALUES (?, ?, ?, ?, ?)",
                (user_id, name, now, now, now)
            )
            await db.commit()

        embed = discord.Embed(
            title="🎉 Новый дракон появился!",
            description=f"**{name}** теперь твой верный спутник!\n\nКорми его, играй и растите вместе.",
            color=0x57F287
        )
        embed.set_footer(text="Используй /dragon info чтобы посмотреть статус")
        await interaction.response.send_message(embed=embed)
        return

    if not dragon:
        await interaction.response.send_message(
            "У тебя ещё нет дракона! Заведи его командой:\n`/dragon create <имя>`",
            ephemeral=True
        )
        return

    # Применяем спад голода/настроения
    dragon = await apply_decay(dragon)

    if action == "info":
        embed = make_embed(dragon)
        await interaction.response.send_message(embed=embed)
        return

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

    if action == "play":
        if dragon["mood"] >= 95:
            await interaction.response.send_message(
                f"**{dragon['name']}** уже полон энергии и счастлив!",
                ephemeral=True
            )
            return

        new_mood = min(MAX_MOOD, dragon["mood"] + PLAY_AMOUNT)
        new_exp = dragon["exp"] + random.randint(8, 15)
        # Игра немного увеличивает голод
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

    if action == "release":
        # Простое подтверждение через ephemeral + followup можно улучшить позже
        await interaction.response.send_message(
            f"Ты уверен, что хочешь отпустить **{dragon['name']}**?\n"
            f"Это действие необратимо.\n\n"
            f"Чтобы подтвердить — напиши в чат: `отпустить {dragon['name']}`",
            ephemeral=True
        )
        return


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
