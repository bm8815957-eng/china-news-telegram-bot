import os
import asyncio
import json
import re
import html
import requests
import feedparser

from bs4 import BeautifulSoup
from telegram import Bot


BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_USERNAME = "@eHTDSNB"

CHECK_INTERVAL = 30 * 60
SEEN_FILE = "seen_news.json"

# China-focused RSS feeds
RSS_FEEDS = [
    "https://www.chinadaily.com.cn/rss/china_rss.xml",
]

# Words that strongly indicate China-related content
CHINA_KEYWORDS = [
    "china",
    "chinese",
    "beijing",
    "shanghai",
    "shenzhen",
    "guangzhou",
    "hong kong",
    "macau",
    "tibet",
    "xinjiang",
    "taiwan",
    "xi jinping",
    "chinese government",
    "chinese economy",
    "chinese company",
    "yuan",
    "renminbi",
    "china's",
]


def load_seen():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_seen(seen):
    recent = list(seen)[-500:]

    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(
            recent,
            f,
            ensure_ascii=False,
            indent=2
        )


def clean_text(text):
    if not text:
        return ""

    text = BeautifulSoup(
        text,
        "html.parser"
    ).get_text(
        " ",
        strip=True
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return html.unescape(text).strip()


def is_china_news(article):
    text = (
        article.get("title", "")
        + " "
        + article.get("summary", "")
    ).lower()

    for keyword in CHINA_KEYWORDS:
        if keyword in text:
            return True

    return False


def get_image_from_article(url):
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "Chrome/146.0 Safari/537.36"
            )
        }

        response = requests.get(
            url,
            headers=headers,
            timeout=20
        )

        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        # Open Graph image
        image = soup.find(
            "meta",
            property="og:image"
        )

        if image:
            image_url = image.get("content")

            if image_url:
                return image_url

        # Twitter image
        image = soup.find(
            "meta",
            attrs={
                "name": "twitter:image"
            }
        )

        if image:
            image_url = image.get("content")

            if image_url:
                return image_url

        # Article image
        article_image = soup.find(
            "img"
        )

        if article_image:
            image_url = (
                article_image.get("src")
                or article_image.get("data-src")
            )

            if image_url:
                return image_url

    except Exception as e:
        print(
            f"⚠️ Image extraction error: {e}"
        )

    return None


def download_image(image_url):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0"
        }

        response = requests.get(
            image_url,
            headers=headers,
            timeout=20
        )

        response.raise_for_status()

        content_type = response.headers.get(
            "content-type",
            ""
        ).lower()

        if not content_type.startswith("image/"):
            print(
                "⚠️ URL did not return an image."
            )
            return None

        # Telegram supports normal image formats.
        image_data = response.content

        if len(image_data) < 5000:
            print(
                "⚠️ Image appears too small."
            )
            return None

        return image_data

    except Exception as e:
        print(
            f"⚠️ Image download error: {e}"
        )

        return None


def get_news():
    articles = []

    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(
                feed_url
            )

            for entry in feed.entries[:20]:

                title = clean_text(
                    entry.get(
                        "title",
                        ""
                    )
                )

                link = entry.get(
                    "link",
                    ""
                )

                summary = clean_text(
                    entry.get(
                        "summary",
                        ""
                    )
                )

                if not title or not link:
                    continue

                article = {
                    "title": title,
                    "link": link,
                    "summary": summary
                }

                # China-only filter
                if not is_china_news(article):
                    print(
                        f"⏭️ Skipped non-China: {title}"
                    )
                    continue

                articles.append(
                    article
                )

        except Exception as e:
            print(
                f"⚠️ RSS error: {e}"
            )

    return articles


def make_chinese_caption(article):
    title = article["title"]
    summary = article["summary"]

    if len(summary) > 450:
        summary = (
            summary[:450]
            .rsplit(" ", 1)[0]
            + "..."
        )

    caption = (
        "🇨🇳 <b>中国新闻</b>\n\n"
        f"📰 <b>{html.escape(title)}</b>\n\n"
        f"{html.escape(summary)}\n\n"
        "━━━━━━━━━━━━━━\n"
        "🔗 <a href=\""
        f"{html.escape(article['link'])}"
        "\">阅读原文</a>\n\n"
        "#中国新闻 #中国 #ChinaNews"
    )

    return caption


async def post_article(bot, article):

    print(
        f"🔎 Checking image: "
        f"{article['title']}"
    )

    image_url = get_image_from_article(
        article["link"]
    )

    # Image is REQUIRED
    if not image_url:
        print(
            "⏭️ Skipped: no image found."
        )
        return False

    image_data = download_image(
        image_url
    )

    if not image_data:
        print(
            "⏭️ Skipped: image unavailable."
        )
        return False

    caption = make_chinese_caption(
        article
    )

    try:

        await bot.send_photo(
            chat_id=CHANNEL_USERNAME,
            photo=image_data,
            caption=caption,
            parse_mode="HTML"
        )

        print(
            f"✅ Posted with image: "
            f"{article['title']}"
        )

        return True

    except Exception as e:

        print(
            f"❌ Telegram error: {e}"
        )

        return False


async def main():

    if not BOT_TOKEN:
        raise ValueError(
            "BOT_TOKEN environment variable "
            "is missing"
        )

    bot = Bot(
        token=BOT_TOKEN
    )

    seen = load_seen()

    print(
        "🤖 China News Bot V2 started!"
    )

    print(
        f"📢 Channel: "
        f"{CHANNEL_USERNAME}"
    )

    print(
        "🇨🇳 China-only mode: ON"
    )

    print(
        "🖼️ Image-required mode: ON"
    )

    while True:

        try:

            articles = get_news()

            print(
                f"🇨🇳 China articles found: "
                f"{len(articles)}"
            )

            new_articles = []

            for article in articles:

                article_id = article["link"]

                if article_id not in seen:

                    new_articles.append(
                        article
                    )

            print(
                f"🆕 New articles: "
                f"{len(new_articles)}"
            )

            # Maximum 3 posts per check
            for article in new_articles[:3]:

                success = await post_article(
                    bot,
                    article
                )

                if success:

                    seen.add(
                        article["link"]
                    )

                    save_seen(
                        seen
                    )

                    await asyncio.sleep(
                        10
                    )

            print(
                "⏰ Waiting 30 minutes..."
            )

            await asyncio.sleep(
                CHECK_INTERVAL
            )

        except Exception as e:

            print(
                f"❌ Main loop error: {e}"
            )

            await asyncio.sleep(
                60
            )


if __name__ == "__main__":
    asyncio.run(main())
