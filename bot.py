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

# Check for new news every 30 minutes
CHECK_INTERVAL = 30 * 60

# File used to remember already-posted articles
SEEN_FILE = "seen_news.json"

RSS_FEEDS = [
    "https://www.chinadaily.com.cn/rss/china_rss.xml",
    "https://www.chinadaily.com.cn/rss/world_rss.xml",
]


def load_seen():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_seen(seen):
    # Keep the file from becoming too large
    recent = list(seen)[-500:]

    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(recent, f, ensure_ascii=False, indent=2)


def clean_text(text):
    if not text:
        return ""

    text = BeautifulSoup(text, "html.parser").get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text)

    return html.unescape(text).strip()


def get_image_from_article(url):
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/146 Safari/537.36"
            )
        }

        response = requests.get(
            url,
            headers=headers,
            timeout=15
        )

        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # Open Graph image
        image = soup.find(
            "meta",
            property="og:image"
        )

        if image and image.get("content"):
            return image["content"]

        # Twitter image
        image = soup.find(
            "meta",
            attrs={"name": "twitter:image"}
        )

        if image and image.get("content"):
            return image["content"]

    except Exception as e:
        print(f"⚠️ Could not get article image: {e}")

    return None


def get_news():
    articles = []

    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)

            for entry in feed.entries[:10]:
                title = clean_text(entry.get("title", ""))
                link = entry.get("link", "")
                summary = clean_text(
                    entry.get("summary", "")
                )

                if not title or not link:
                    continue

                articles.append({
                    "title": title,
                    "link": link,
                    "summary": summary
                })

        except Exception as e:
            print(f"⚠️ RSS error: {e}")

    return articles


def make_caption(article):
    title = article["title"]
    summary = article["summary"]

    # Limit summary length
    if len(summary) > 500:
        summary = summary[:500].rsplit(" ", 1)[0] + "..."

    caption = (
        f"🇨🇳 <b>{html.escape(title)}</b>\n\n"
        f"📰 {html.escape(summary)}\n\n"
        f"🔗 <a href=\"{html.escape(article['link'])}\">查看原文</a>\n\n"
        f"#中国新闻 #中国 #ChinaNews"
    )

    return caption


async def post_article(bot, article):
    image_url = get_image_from_article(article["link"])
    caption = make_caption(article)

    try:
        if image_url:
            image_response = requests.get(
                image_url,
                timeout=20,
                headers={
                    "User-Agent": "Mozilla/5.0"
                }
            )

            image_response.raise_for_status()

            image_data = image_response.content

            await bot.send_photo(
                chat_id=CHANNEL_USERNAME,
                photo=image_data,
                caption=caption,
                parse_mode="HTML"
            )

            print(
                f"🖼️ Posted with image: "
                f"{article['title']}"
            )

        else:
            await bot.send_message(
                chat_id=CHANNEL_USERNAME,
                text=caption,
                parse_mode="HTML",
                disable_web_page_preview=False
            )

            print(
                f"📰 Posted without image: "
                f"{article['title']}"
            )

        return True

    except Exception as e:
        print(f"❌ Telegram posting error: {e}")
        return False


async def main():
    if not BOT_TOKEN:
        raise ValueError(
            "BOT_TOKEN environment variable is missing"
        )

    bot = Bot(token=BOT_TOKEN)

    seen = load_seen()

    print("🤖 China News Bot started!")
    print(f"📢 Channel: {CHANNEL_USERNAME}")

    while True:
        try:
            articles = get_news()

            print(
                f"📰 Found {len(articles)} news articles."
            )

            # Newest articles first
            new_articles = []

            for article in articles:
                article_id = article["link"]

                if article_id not in seen:
                    new_articles.append(article)

            # Post up to 3 new articles per check
            for article in new_articles[:3]:
                success = await post_article(
                    bot,
                    article
                )

                if success:
                    seen.add(article["link"])
                    save_seen(seen)

                    # Small delay between posts
                    await asyncio.sleep(10)

            print(
                f"⏰ Waiting {CHECK_INTERVAL // 60} minutes..."
            )

            await asyncio.sleep(CHECK_INTERVAL)

        except Exception as e:
            print(f"❌ Main loop error: {e}")

            # Don't kill the bot if one request fails
            await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(main())
