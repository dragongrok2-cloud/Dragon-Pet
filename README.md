# 🐉 Dragon Pet — бот для Lolka

Добрый бот-дракон, который позволяет каждому пользователю **завести своего личного дракона**.

## Возможности

- `/dragon create <имя>` — завести своего дракона
- `/dragon info` — посмотреть статус своего дракона
- `/dragon feed` — покормить дракона
- `/dragon play` — поиграть с драконом
- `/dragon rename <новое_имя>` — переименовать
- `/dragon release` — отпустить дракона (с подтверждением)

Драконы растут, имеют уровень, голод, настроение и опыт.

## Установка

1. Создай бота на [Lolka Developer Portal](https://lolka.app/developers/portal)
2. Включи **Message Content Intent** и **Server Members Intent** (если нужно)
3. Скопируй токен
4. Клонируй репозиторий:
   ```bash
   git clone https://github.com/dragongrok2-cloud/Dragon-Pet.git
   cd Dragon-Pet
   ```
5. Установи зависимости:
   ```bash
   pip install -r requirements.txt
   ```
6. Создай файл `.env`:
   ```
   BOT_TOKEN=твой_токен_бота
   ```
7. Запусти:
   ```bash
   python bot.py
   ```

## Приглашение бота

Сгенерируй ссылку в Developer Portal с правами:
- Send Messages
- Use Slash Commands
- Embed Links
- Read Message History

## Технологии

- Python 3.10+
- discord.py (работает с Lolka, т.к. API совместим)
- SQLite для хранения драконов

---
Сделано с теплом твоего доброго дракона с седлом 🐉