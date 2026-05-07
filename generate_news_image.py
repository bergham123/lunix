import feedparser
import requests
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
import arabic_reshaper
from bidi.algorithm import get_display
import os
import re

# ============================================================
# CONFIGURATION - Change these as needed
# ============================================================
RSS_URL = "https://www.telegraphe.ma/rss/latest-posts"
OUTPUT_IMAGE = "output.webp"           # File to save in your repo
LAST_ARTICLE_FILE = "last_article.txt" # Tracks last processed article

# ============================================================
# IMAGE DIMENSIONS (match your example style)
# ============================================================
WIDTH, HEIGHT = 1280, 720               # 16:9 landscape
TEXT_AREA_HEIGHT = 200                  # height of the semi-transparent bar at bottom
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"  # Linux default font

# ============================================================
# ARABIC TEXT HELPERS
# ============================================================
def fix_arabic_text(text: str) -> str:
    """Reshape Arabic text and fix its direction for proper display."""
    reshaped = arabic_reshaper.reshape(text)
    return get_display(reshaped)

def format_date(date_struct) -> str:
    """Convert feedparser date to DD/MM/YYYY format."""
    if date_struct:
        try:
            return datetime(*date_struct[:6]).strftime("%d/%m/%Y")
        except:
            pass
    return datetime.now().strftime("%d/%m/%Y")

def clean_html(text: str) -> str:
    """Remove HTML tags and decode entities."""
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('&nbsp;', ' ').replace('&amp;', '&')
    return text.strip()

def fetch_latest_article():
    """Get the most recent article from RSS feed."""
    feed = feedparser.parse(RSS_URL)
    
    if not feed.entries:
        print("❌ No entries found in RSS feed.")
        return None
        
    latest = feed.entries[0]  # First entry = newest
    print(f"📰 Found: {latest.title}")
    return latest

def download_image(url: str) -> Image.Image:
    """Download image from URL and return PIL Image object."""
    try:
        response = requests.get(url, timeout=15, stream=True)
        response.raise_for_status()
        img = Image.open(response.raw).convert("RGB")
        print("✅ Image downloaded successfully.")
        return img
    except Exception as e:
        print(f"⚠️ Failed to download image: {e}")
        return None

def create_news_image(article):
    """
    Main image creation function.
    Places title and date on bottom overlay (like the example).
    """
    # 1. Get the article image (or use solid fallback)
    image_url = None
    if hasattr(article, 'media_content') and article.media_content:
        image_url = article.media_content[0]['url']
    elif hasattr(article, 'links'):
        for link in article.links:
            if link.get('type', '').startswith('image/'):
                image_url = link['href']
                break
    
    if image_url:
        background = download_image(image_url)
    else:
        print("⚠️ No image found in RSS, using gradient fallback.")
        background = None
    
    # Create canvas with fallback if no image
    if background:
        background = background.resize((WIDTH, HEIGHT), Image.LANCZOS)
        canvas = background.convert("RGBA")
    else:
        # Fallback: gradient background
        canvas = Image.new("RGBA", (WIDTH, HEIGHT), (25, 40, 65, 255))
        draw = ImageDraw.Draw(canvas)
        for i in range(HEIGHT):
            t = i / HEIGHT
            r = int(10 + t * 20)
            g = int(22 + t * 40)
            b = int(40 + t * 70)
            draw.line([(0, i), (WIDTH, i)], fill=(r, g, b))
    
    # 2. Create semi‑transparent overlay at bottom (like your example's dark bar)
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw_overlay = ImageDraw.Draw(overlay)
    
    # Draw dark bar at bottom with 70% opacity
    bar_height = TEXT_AREA_HEIGHT
    draw_overlay.rectangle(
        [(0, HEIGHT - bar_height), (WIDTH, HEIGHT)],
        fill=(0, 0, 0, 180)  # black, 70% opacity
    )
    
    # Optional: add a subtle gradient to the bar
    for i in range(bar_height):
        t = i / bar_height
        alpha = int(180 * (1 - t * 0.3))  # slight fade at top edge
        draw_overlay.line(
            [(0, HEIGHT - bar_height + i), (WIDTH, HEIGHT - bar_height + i)],
            fill=(0, 0, 0, alpha)
        )
    
    # Composite the overlay onto the canvas
    canvas = Image.alpha_composite(canvas, overlay)
    
    # 3. Prepare Arab ci text
    title = clean_html(article.title)
    pub_date = format_date(getattr(article, 'published_parsed', None))
    
    fixed_title = fix_arabic_text(title)
    fixed_date = fix_arabic_text(pub_date)
    
    # Load font (adjust size as needed)
    try:
        font_title = ImageFont.truetype(FONT_PATH, 42)
        font_date = ImageFont.truetype(FONT_PATH, 28)
    except:
        # Fallback to default if font not found
        font_title = ImageFont.load_default()
        font_date = ImageFont.load_default()
    
    draw = ImageDraw.Draw(canvas)
    
    # 4. Position text inside the bottom bar
    
    # Title – centered with right‑to‑left orientation
    bbox = draw.textbbox((0, 0), fixed_title, font=font_title)
    title_width = bbox[2] - bbox[0]
    title_height = bbox[3] - bbox[1]
    title_x = (WIDTH - title_width) // 2
    title_y = HEIGHT - bar_height + (bar_height - title_height) // 2 - 15
    
    draw.text((title_x, title_y), fixed_title, fill=(255, 255, 255), font=font_title)
    
    # Date – placed to the right, smaller size
    bbox = draw.textbbox((0, 0), fixed_date, font=font_date)
    date_width = bbox[2] - bbox[0]
    date_x = WIDTH - date_width - 30
    date_y = title_y + title_height + 5
    
    draw.text((date_x, date_y), fixed_date, fill=(200, 200, 200), font=font_date)
    
    # 5. Save image
    canvas = canvas.convert("RGB")
    canvas.save(OUTPUT_IMAGE, "WEBP", quality=90)
    print(f"✅ Image saved as {OUTPUT_IMAGE}")
    return OUTPUT_IMAGE

def already_processed(article_id: str) -> bool:
    """Check if this article has been processed before."""
    if not os.path.exists(LAST_ARTICLE_FILE):
        return False
    with open(LAST_ARTICLE_FILE, "r") as f:
        processed = f.read().strip().split("\n")
    return article_id in processed

def mark_processed(article_id: str):
    """Mark article as processed."""
    with open(LAST_ARTICLE_FILE, "a") as f:
        f.write(f"{article_id}\n")

def main():
    print("🚀 Starting news image generator...")
    article = fetch_latest_article()
    
    if not article:
        print("❌ No article fetched. Exiting.")
        return
    
    # Use article link as unique ID
    article_id = article.link if hasattr(article, 'link') else article.title
    if already_processed(article_id):
        print("ℹ️ Latest article already processed. Exiting.")
        return
    
    create_news_image(article)
    mark_processed(article_id)
    
    # This will be saved as output.webp – GitHub Action will commit it
    print("✨ Done!")

if __name__ == "__main__":
    main()
