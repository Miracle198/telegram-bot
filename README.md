# 🪐 Anime Vibe Autoposter Bot

An advanced, asynchronous Telegram bot that automatically generates and posts aesthetic anime pictures with motivational English quotes to a specific channel or chat daily at 10:00 (EET timezone).

## 🛠️ Technical Features
- **Asynchronous Architecture:** Built using `aiogram 3.x` and `APScheduler` for smooth, non-blocking operation.
- **Automated Content Sourcing:** Automatically fetches random high-quality anime images from public APIs (`nekos.best` / `waifu.pics`) with built-in failover backup.
- **On-the-Fly Image Processing:** Uses `Pillow (PIL)` to download images straight into RAM (`BytesIO`), processes them without any disk I/O, applies smooth dark gradients, blurred drop shadows, and professional typography using the `Montserrat` font.
- **Robust Error Handling:** Thread-safe operations (`asyncio.to_thread`) to ensure 100% uptime. Admins are automatically notified via PM if any external API fails.

## 📦 Tech Stack
- Python 3.10+
- Aiogram 3.x
- Pillow (PIL)
- Requests & Loggers
- APScheduler
- Pytz (Timezones)

## 🔧 Installation & Setup
1. Clone this repository.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy `config.example.json` to `config.json` and fill in your Telegram Bot Token, Channel ID, and Admin IDs.
4. Place your preferred `.ttf` font (e.g., `Montserrat-Bold.ttf`) into the root directory.
5. Run the bot:
   ```bash
   python bot.py
   ```

## 🤖 Commands
- `/start` - Check your Telegram User ID.
- `/test_anime` - (Admins only) Instantly trigger image generation and post it to the channel for testing purposes.
