import feedparser
import requests
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
import arabic_reshaper
from bidi.algorithm import get_display
import os
import sys
import re

# ============================================================
# CONFIGURATION
# ============================================================
RSS_URL = "https://www.telegraphe.ma/rss/latest-posts"
OUTPUT_IMAGE = "output.webp"
LAST_ARTICLE_FILE = "last_article.txt"

WIDTH, HEIGHT = 1280, 720
BAR_HEIGHT = 200   # height of the dark bottom bar

# ============================================================
# ARABIC TEXT HELPERS
# ============================================================
def fix_arabic(text: str) -> str:
    """Reshape and flip Arabic text for correct display."""
    reshaped = arabic_reshaper.reshape(text)
    return get_display(reshaped)

def clean_html(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', '', text)
    return text.strip()

def get_date(entry) -> str:
    """Extract date from feed entry or use today."""
    if hasattr(entry, 'published_parsed') and entry.published_parsed:
        return datetime(*entry.published_parsed[:6]).strftime("%d/%m/%Y")
    elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
        return datetime(*entry.updated_parsed[:6]).strftime("%d/%m/%Y")
    return datetime.now().strftime("%d/%m/%Y")

def get_image_url(entry):
    """Extract image URL from various possible RSS fields."""
    # Try media:content
    if hasattr(entry, 'media_content') and entry.media_content:
        return entry.media_content[0]['url']
    # Try enclosure
    if hasattr(entry, 'enclosures') and entry.enclosures:
        for enc in entry.enclosures:
            if enc.get('type', '').startswith('image/'):
                return enc['href']
    # Try regex in description
    if hasattr(entry, 'description') and entry.description:
        match = re.search(r'src="([^"]+)"', entry.description)
        if match:
            return match.group(1)
    # Try link to an image (if direct)
    if hasattr(entry, 'link') and entry.link.endswith(('.jpg', '.png', '.webp')):
        return entry.link
    return None

def load_font(size):
    """Load a font – tries common Linux paths, then falls back to default."""
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/System/Library/Fonts/Helvetica.ttc",  # for local macOS testing
        "/Windows/Fonts/arial.ttf",             # for local Windows
    ]
    for path in font_paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except:
                continue
    # Ultimate fallback – PIL default font (will be tiny but visible)
    print("⚠️ No TTF font found – using default PIL font (text may be small)")
    return ImageFont.load_default()

# ============================================================
# MAIN IMAGE CREATION
# ============================================================
def create_news_image(entry):
    print("🖼️ Creating image...")

    # 1. Fetch background image (or use solid color)
    img_url = get_image_url(entry)
    bg = None
    if img_url:
        try:
            r = requests.get(img_url, timeout=15, stream=True)
            if r.status_code == 200:
                bg = Image.open(r.raw).convert("RGB")
                bg = bg.resize((WIDTH, HEIGHT), Image.LANCZOS)
                print("✅ Background image loaded")
            else:
                print(f"⚠️ Image download failed (status {r.status_code})")
        except Exception as e:
            print(f"⚠️ Image error: {e}")
    
    if bg is None:
        # Fallback: gradient background
        bg = Image.new("RGB", (WIDTH, HEIGHT), (20, 30, 50))
        draw = ImageDraw.Draw(bg)
        for i in range(HEIGHT):
            t = i / HEIGHT
            r = int(20 + t * 30)
            g = int(30 + t * 40)
            b = int(50 + t * 60)
            draw.line([(0, i), (WIDTH, i)], fill=(r, g, b))
        print("ℹ️ Using gradient fallback background")

    # 2. Create overlay for dark bottom bar
    overlay = Image.new("RGBA", bg.size, (0, 0, 0, 0))
    draw_overlay = ImageDraw.Draw(overlay)
    draw_overlay.rectangle(
        [(0, HEIGHT - BAR_HEIGHT), (WIDTH, HEIGHT)],
        fill=(0, 0, 0, 200)   # black with 78% opacity
    )
    # Optional: softer top edge
    for i in range(20):
        alpha = int(200 * (1 - i/20))
        draw_overlay.line(
            [(0, HEIGHT - BAR_HEIGHT + i), (WIDTH, HEIGHT - BAR_HEIGHT + i)],
            fill=(0, 0, 0, alpha)
        )

    # Composite overlay onto background
    final = Image.alpha_composite(bg.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(final)

    # 3. Prepare Arabic text
    title_raw = clean_html(entry.title)
    date_raw = get_date(entry)
    print(f"📝 Title: {title_raw}")
    print(f"📅 Date: {date_raw}")

    title_arab = fix_arabic(title_raw)
    date_arab = fix_arabic(date_raw)

    # 4. Load fonts (sizes adjusted for 1280x720)
    font_title = load_font(48)
    font_date = load_font(32)

    # Measure text size (for centering)
    # Note: textbbox may be inaccurate with default font, but we try
    try:
        bbox = draw.textbbox((0, 0), title_arab, font=font_title)
        title_w = bbox[2] - bbox[0]
        title_h = bbox[3] - bbox[1]
    except:
        title_w, title_h = draw.textsize(title_arab, font=font_title) if hasattr(draw, "textsize") else (WIDTH//2, 40)
    
    # Position title – centered horizontally, vertically inside the bar
    title_x = (WIDTH - title_w) // 2
    # Title starts about 40px above the bar's middle
    title_y = HEIGHT - BAR_HEIGHT + (BAR_HEIGHT - title_h) // 2 - 10

    # Draw title with shadow for readability
    draw.text((title_x + 2, title_y + 2), title_arab, fill=(0, 0, 0, 150), font=font_title)
    draw.text((title_x, title_y), title_arab, fill=(255, 255, 255), font=font_title)
    print(f"✅ Title drawn at ({title_x}, {title_y})")

    # Draw date – bottom right inside the bar
    try:
        bbox = draw.textbbox((0, 0), date_arab, font=font_date)
        date_w = bbox[2] - bbox[0]
        date_h = bbox[3] - bbox[1]
    except:
        date_w, date_h = draw.textsize(date_arab, font=font_date) if hasattr(draw, "textsize") else (100, 30)
    date_x = WIDTH - date_w - 30
    date_y = HEIGHT - BAR_HEIGHT + (BAR_HEIGHT - date_h) // 2 + 15

    draw.text((date_x + 1, date_y + 1), date_arab, fill=(0, 0, 0, 150), font=font_date)
    draw.text((date_x, date_y), date_arab, fill=(220, 220, 220), font=font_date)
    print(f"✅ Date drawn at ({date_x}, {date_y})")

    # 5. Save image
    final.save(OUTPUT_IMAGE, "WEBP", quality=90)
    print(f"💾 Saved as {OUTPUT_IMAGE}")
    return OUTPUT_IMAGE

# ============================================================
# TRACKING AND MAIN
# ============================================================
def already_processed(article_id):
    if not os.path.exists(LAST_ARTICLE_FILE):
        return False
    with open(LAST_ARTICLE_FILE, 'r') as f:
        return article_id in f.read()

def mark_processed(article_id):
    with open(LAST_ARTICLE_FILE, 'a') as f:
        f.write(f"{article_id}\n")

def main():
    print("🚀 Fetching RSS...")
    feed = feedparser.parse(RSS_URL)
    if not feed.entries:
        print("❌ No entries found.")
        return
    
    latest = feed.entries[0]
    article_id = latest.link if hasattr(latest, 'link') else latest.title
    if already_processed(article_id):
        print("ℹ️ Already processed, skipping.")
        return
    
    print(f"📰 Processing: {latest.title}")
    create_news_image(latest)
    mark_processed(article_id)
    print("✨ Done.")

if __name__ == "__main__":
    main()
