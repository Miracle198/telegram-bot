"""
Image generation module.

1. Fetches a random SFW anime image from a free public API (nekos.best, with
   waifu.pics as a backup) and downloads it straight into memory (BytesIO).
   Nothing is read from or written to the disk.
2. Overlays a random English quote using the Montserrat-Bold font.

The module does not depend on Telegram, so it can be tested on its own.
"""

from __future__ import annotations

import logging
import random
from functools import lru_cache
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

# =====================================================================
# 1. CONSTANTS
# =====================================================================

# --- Quotes (strictly English) ---
PHRASES = [
    "Every day is a new page of your story",
    "Stars can't shine without darkness",
    "Good evening. You made it through another day",
    "Small steps still move you forward",
    "Be gentle with yourself tonight",
    "Rest is part of the journey",
    "You are stronger than you think",
    "The best chapters are still unwritten",
    "Let the night be soft and the dreams be kind",
    "Breathe in. Breathe out. You are doing great",
    "Even the moon needs time to glow again",
    "Collect moments, not worries",
    "Tonight, let your heart feel at home",
    "Believe in the magic of new beginnings",
    "Your potential is endless. Keep going",
    "Quiet minds find the best answers",
    "Don't count the days, make the days count",
    "Focus on the good, and the good will grow",
    "Big dreams require time and patience",
    "You don't have to figure it all out tonight",
    "Stay close to what keeps you alive",
    "Tomorrow is a blank canvas. Paint it well",
    "Be proud of how hard you are trying",
    "The sun will rise and we will try again",
    "Create your own sunshine on cloudy days",
    "Keep moving forward, no matter the pace",
    "Peace over panic. Calm over chaos",
    "You are doing much better than you realize"
]

# --- Fonts ---
# Default font: put "Montserrat-Bold.ttf" in the project root (next to this file)
DEFAULT_FONT = Path(__file__).parent / "Montserrat-Bold.ttf"

# Fallback fonts, used only if the font above is missing
FALLBACK_FONTS = [
    "C:/Windows/Fonts/arialbd.ttf",                                   # Windows
    "C:/Windows/Fonts/segoeuib.ttf",                                  # Windows
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",           # Linux
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",   # Linux
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",              # macOS
]

# --- Image API ---
# Both services return SFW images only. Each source is tried in turn.
NEKOS_BEST_CATEGORIES = ["waifu", "neko", "kitsune"]
WAIFU_PICS_URL = "https://api.waifu.pics/sfw/waifu"

REQUEST_TIMEOUT = (10, 30)          # (connect, read) timeouts in seconds
MAX_ATTEMPTS = 3                    # how many full rounds over all sources
MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024  # refuse files larger than 20 MB
USER_AGENT = "AnimeChannelBot/2.0 (Telegram daily poster)"

MAX_SIDE = 1600  # the longer side of the final picture (px)


# =====================================================================
# 2. FETCHING THE IMAGE FROM THE API
# =====================================================================

def _url_from_nekos_best(session: requests.Session) -> str:
    """Asks nekos.best for a random image URL."""
    category = random.choice(NEKOS_BEST_CATEGORIES)
    response = session.get(f"https://nekos.best/api/v2/{category}", timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()["results"][0]["url"]


def _url_from_waifu_pics(session: requests.Session) -> str:
    """Asks waifu.pics for a random SFW image URL (backup source)."""
    response = session.get(WAIFU_PICS_URL, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()["url"]


def _download(session: requests.Session, url: str) -> bytes:
    """Downloads the file by URL into memory and checks that it is a real image."""
    response = session.get(url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()

    data = response.content
    if len(data) > MAX_DOWNLOAD_BYTES:
        raise ValueError(f"Image is too large: {len(data) / 1024 / 1024:.1f} MB")

    # Make sure the bytes are a valid image (raises an error otherwise)
    with Image.open(BytesIO(data)) as probe:
        probe.verify()
    return data


def fetch_anime_image() -> bytes:
    """
    Returns the bytes of a random anime image.
    Tries every API source, repeating up to MAX_ATTEMPTS rounds if something fails.
    """
    sources = [("nekos.best", _url_from_nekos_best), ("waifu.pics", _url_from_waifu_pics)]
    last_error: Exception | None = None

    with requests.Session() as session:
        session.headers["User-Agent"] = USER_AGENT
        for attempt in range(1, MAX_ATTEMPTS + 1):
            for name, get_url in sources:
                try:
                    url = get_url(session)
                    data = _download(session, url)
                    logging.info("Image fetched from %s (%d KB)", name, len(data) // 1024)
                    return data
                except Exception as error:  # network error, bad JSON, broken image...
                    last_error = error
                    logging.warning("Attempt %d, source %s failed: %s", attempt, name, error)

    raise RuntimeError(f"Could not fetch an image from the APIs: {last_error}")


# =====================================================================
# 3. FONTS AND TEXT HELPERS
# =====================================================================

@lru_cache(maxsize=None)
def resolve_font_path(custom_path: str | None) -> str | None:
    """Finds the first existing font file: custom -> Montserrat-Bold -> system fallbacks."""
    candidates = [custom_path, str(DEFAULT_FONT), *FALLBACK_FONTS]
    for path in candidates:
        if path and Path(path).exists():
            if path not in (custom_path, str(DEFAULT_FONT)):
                logging.warning("Montserrat-Bold.ttf not found, using fallback font: %s", path)
            return path
    logging.warning("No suitable font found, using Pillow's built-in font (may lack styling).")
    return None


def load_font(custom_path: str | None, size: int) -> ImageFont.FreeTypeFont:
    """Loads the font at the given size."""
    path = resolve_font_path(custom_path)
    if path:
        return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Splits the text into lines so that each line fits into max_width pixels."""
    lines: list[str] = []
    current = ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        if font.getlength(trial) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def add_bottom_gradient(image: Image.Image, height_ratio: float = 0.5) -> None:
    """Darkens the bottom of the picture with a smooth gradient so the text stays readable."""
    width, height = image.size
    grad_h = int(height * height_ratio)
    mask = Image.linear_gradient("L").resize((width, grad_h))  # black (top) -> white (bottom)
    mask = mask.point(lambda v: int(v * 0.78))                 # max opacity 78%
    image.paste((0, 0, 0), (0, height - grad_h), mask)


def draw_text_with_shadow(
    image: Image.Image,
    lines: list[str],
    font: ImageFont.FreeTypeFont,
    top_y: int,
    line_height: int,
) -> None:
    """Draws centered white text with a soft blurred drop shadow."""
    width = image.width
    center_x = width / 2
    offset = max(2, font.size // 16)

    # 1) Shadow: draw black text on a transparent layer and blur it
    shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    y = top_y
    for line in lines:
        shadow_draw.text((center_x + offset, y + offset), line, font=font,
                         fill=(0, 0, 0, 230), anchor="ma")
        y += line_height
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=max(3, font.size // 10)))
    image.paste(shadow, (0, 0), shadow)

    # 2) The text itself on top of the shadow
    draw = ImageDraw.Draw(image)
    y = top_y
    for line in lines:
        draw.text((center_x, y), line, font=font, fill=(255, 255, 255), anchor="ma")
        y += line_height

    # 3) Thin accent line above the quote for a clean, polished look
    line_w = max(60, width // 10)
    line_y = top_y - max(14, font.size // 2)
    draw.rounded_rectangle(
        (center_x - line_w / 2, line_y, center_x + line_w / 2, line_y + max(3, font.size // 14)),
        radius=2,
        fill=(255, 255, 255),
    )


# =====================================================================
# 4. MAIN FUNCTION
# =====================================================================

def create_image(font_path: str | None = None) -> tuple[BytesIO, str]:
    """
    Fetches an anime image from the API, overlays a random English quote.
    Returns (JPEG data in memory, the quote that was used).
    This function is blocking — call it via asyncio.to_thread() from async code.
    """
    phrase = random.choice(PHRASES)

    # Download the image into memory and open it from there
    raw = fetch_anime_image()
    image = Image.open(BytesIO(raw)).convert("RGB")  # RGB: handles PNG/WEBP with transparency
    image.thumbnail((MAX_SIDE, MAX_SIDE))            # shrink oversized pictures
    width, height = image.size

    add_bottom_gradient(image)

    # Pick the biggest font size where the quote fits in the bottom 35% / 86% of the width
    max_text_width = int(width * 0.86)
    max_text_height = int(height * 0.30)
    font_size = max(24, width // 13)
    while True:
        font = load_font(font_path, font_size)
        lines = wrap_text(phrase, font, max_text_width)
        line_height = int(font_size * 1.3)
        if len(lines) * line_height <= max_text_height or font_size <= 24:
            break
        font_size -= 2

    block_height = len(lines) * line_height
    top_y = height - block_height - int(height * 0.06)
    draw_text_with_shadow(image, lines, font, top_y, line_height)

    # Save to memory (no disk access)
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=92, optimize=True)
    buffer.seek(0)
    return buffer, phrase
