import os
import asyncio
import json
import re
import html
from urllib.parse import urljoin

import requests
import feedparser
from bs4 import BeautifulSoup
from telegram import Bot


# =========================================================
# SETTINGS
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_USERNAME = "@eHTDSNB"

CHECK_INTERVAL = 30 * 60  # 30 minutes
SEEN_FILE = "seen_news.json"

MAX_POSTS_PER_CHECK = 3


# =========================================================
# CHINA NEWS RSS FEEDS
# =========================================================

RSS_FEEDS = [
    "https://www.chinadaily.com.cn/rss/china_rss.xml",
]


# =========================================================
# CHINA KEYWORDS
# =========================================================

CHINA_KEYWORDS = [
    "china",
    "chinese",
    "beijing",
    "shanghai",
    "shenzhen",
    "guangzhou",
    "tianjin",
    "chengdu",
    "hong kong",
    "macau",
    "tibet",
    "xinjiang",
    "taiwan",
    "xi jinping",
    "chinese government",
    "chinese economy",
    "chinese company",
    "chinese market",
    "yuan",
    "renminbi",
    "china's",
]


# =========================================================
# HTTP HEADERS
# =========================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/146.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# =========================================================
# LOAD SEEN NEWS
# =========================================================

def load_seen():
    try:
        with open(
            SEEN_FILE,
            "r",
            encoding="utf-8"
        ) as file:
            return set(json.load(file))

    except Exception:
        return set()


# =========================================================
# SAVE SEEN NEWS
# =========================================================

def save_seen(seen):
    # Keep only the latest 500 article links
    recent = list(seen)[-500:]

    with open(
        SEEN_FILE,
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            recent,
            file,
            ensure_ascii=False,
            indent=2
        )


# =========================================================
# CLEAN TEXT
# =========================================================

def clean_text(text):

    if not text:
        return ""

    soup = BeautifulSoup(
        text,
        "html.parser"
    )

    text = soup.get_text(
        " ",
        strip=True
    )

    text = html.unescape(text)

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# =========================================================
# CHECK IF ARTICLE IS ABOUT CHINA
# =========================================================

def is_china_news(title, summary):

    text = (
        title
        + " "
        + summary
    ).lower()

    for keyword in CHINA_KEYWORDS:

        if keyword in text:
            return True

    return False


# =========================================================
# GET RSS NEWS
# =========================================================

def get_news():

    articles = []

    for feed_url in RSS_FEEDS:

        try:

            print(
                f"📡 Reading feed: {feed_url}"
            )

            feed = feedparser.parse(
                feed_url
            )

            for entry in feed.entries[:30]:

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

                if not is_china_news(
                    title,
                    summary
                ):

                    print(
                        f"⏭️ Not China news: "
                        f"{title}"
                    )

                    continue

                article = {
                    "title": title,
                    "link": link,
                    "summary": summary
                }

                articles.append(
                    article
                )

        except Exception as error:

            print(
                f"❌ RSS error: {error}"
            )

    return articles


# =========================================================
# FIND ARTICLE IMAGE
# =========================================================

def find_article_image(article_url):

    try:

        print(
            f"🔎 Looking for image: "
            f"{article_url}"
        )

        response = requests.get(
            article_url,
            headers=HEADERS,
            timeout=20
        )

        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        candidates = []

        # -------------------------------------------------
        # OpenGraph image
        # -------------------------------------------------

        for meta in soup.find_all(
            "meta",
            property="og:image"
        ):

            image = meta.get(
                "content"
            )

            if image:
                candidates.append(
                    image
                )

        # -------------------------------------------------
        # Twitter image
        # -------------------------------------------------

        for meta in soup.find_all(
            "meta",
            attrs={
                "name": "twitter:image"
            }
        ):

            image = meta.get(
                "content"
            )

            if image:
                candidates.append(
                    image
                )

        # -------------------------------------------------
        # Other Twitter card format
        # -------------------------------------------------

        for meta in soup.find_all(
            "meta",
            attrs={
                "property": "twitter:image"
            }
        ):

            image = meta.get(
                "content"
            )

            if image:
                candidates.append(
                    image
                )

        # -------------------------------------------------
        # Article images
        # -------------------------------------------------

        for img in soup.find_all(
            "img"
        ):

            image = (
                img.get("src")
                or img.get("data-src")
                or img.get("data-original")
                or img.get("data-lazy-src")
            )

            if image:
                candidates.append(
                    image
                )

        # -------------------------------------------------
        # Process candidates
        # -------------------------------------------------

        for image_url in candidates:

            if not image_url:
                continue

            image_url = image_url.strip()

            # ---------------------------------------------
            # Protocol-relative URL
            # Example:
            # //www.example.com/image.jpg
            # ---------------------------------------------

            if image_url.startswith("//"):

                image_url = (
                    "https:"
                    + image_url
                )

            # ---------------------------------------------
            # Relative URL
            # ---------------------------------------------

            elif image_url.startswith("/"):

                image_url = urljoin(
                    article_url,
                    image_url
                )

            # ---------------------------------------------
            # Other relative URL
            # ---------------------------------------------

            elif not image_url.startswith(
                (
                    "http://",
                    "https://"
                )
            ):

                image_url = urljoin(
                    article_url,
                    image_url
                )

            # ---------------------------------------------
            # Ignore bad URLs
            # ---------------------------------------------

            if not image_url.startswith(
                (
                    "http://",
                    "https://"
                )
            ):
                continue

            lower_url = image_url.lower()

            # ---------------------------------------------
            # Reject logos/icons
            # ---------------------------------------------

            blocked_words = [
                "logo",
                "favicon",
                "avatar",
                "icon",
                "placeholder",
                "sprite",
                "qrcode",
                "qr-code",
            ]

            if any(
                word in lower_url
                for word in blocked_words
            ):

                print(
                    f"⏭️ Ignoring logo/icon: "
                    f"{image_url}"
                )

                continue

            print(
                f"🖼️ Image candidate: "
                f"{image_url}"
            )

            # ---------------------------------------------
            # Verify image
            # ---------------------------------------------

            try:

                image_response = requests.get(
                    image_url,
                    headers=HEADERS,
                    timeout=20
                )

                image_response.raise_for_status()

                content_type = (
                    image_response
                    .headers
                    .get(
                        "content-type",
                        ""
                    )
                    .lower()
                )

                if not content_type.startswith(
                    "image/"
                ):

                    print(
                        "⏭️ Not an image."
                    )

                    continue

                image_data = (
                    image_response.content
                )

                # Reject tiny images
                if len(image_data) < 10000:

                    print(
                        "⏭️ Image too small."
                    )

                    continue

                print(
                    "✅ Valid news image found."
                )

                return image_data

            except Exception as error:

                print(
                    f"⚠️ Image candidate failed: "
                    f"{error}"
                )

        print(
            "❌ No usable news image found."
        )

        return None

    except Exception as error:

        print(
            f"❌ Article image error: "
            f"{error}"
        )

        return None


# =========================================================
# CREATE TELEGRAM CAPTION
# =========================================================

def make_caption(article):

    title = article["title"]
    summary = article["summary"]

    # Clean title
    title = clean_text(
        title
    )

    # Clean summary
    summary = clean_text(
        summary
    )

    # Limit summary
    if len(summary) > 500:

        summary = (
            summary[:500]
            .rsplit(
                " ",
                1
            )[0]
            + "..."
        )

    # If RSS doesn't provide summary
    if not summary:

        summary = (
            "中国最新消息受到关注，"
            "相关情况正在持续发展。"
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


# =========================================================
# POST ARTICLE
# =========================================================

async def post_article(
    bot,
    article
):

    print(
        "\n"
        "================================"
    )

    print(
        f"📰 Article: "
        f"{article['title']}"
    )

    print(
        "================================"
    )

    # Image REQUIRED
    image_data = find_article_image(
        article["link"]
    )

    if not image_data:

        print(
            "⏭️ SKIPPED — "
            "article has no usable image."
        )

        return False

    caption = make_caption(
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
            "✅ POSTED WITH IMAGE!"
        )

        return True

    except Exception as error:

        print(
            f"❌ Telegram posting error: "
            f"{error}"
        )

        return False


# =========================================================
# MAIN BOT
# =========================================================

async def main():

    if not BOT_TOKEN:

        raise ValueError(
            "BOT_TOKEN environment variable "
            "is missing."
        )

    bot = Bot(
        token=BOT_TOKEN
    )

    seen = load_seen()

    print(
        "================================"
    )

    print(
        "🤖 China News Bot V2"
    )

    print(
        "================================"
    )

    print(
        f"📢 Channel: "
        f"{CHANNEL_USERNAME}"
    )

    print(
        "🇨🇳 China-only: ENABLED"
    )

    print(
        "🖼️ Image-required: ENABLED"
    )

    print(
        "🚫 Duplicate protection: ENABLED"
    )

    print(
        "⏰ Check interval: 30 minutes"
    )

    print(
        "================================"
    )

    while True:

        try:

            print(
                "\n🔄 Checking for new news..."
            )

            articles = get_news()

            print(
                f"🇨🇳 China articles found: "
                f"{len(articles)}"
            )

            new_articles = []

            for article in articles:

                article_id = article["link"]

                if article_id in seen:

                    print(
                        f"♻️ Already posted: "
                        f"{article['title']}"
                    )

                    continue

                new_articles.append(
                    article
                )

            print(
                f"🆕 New articles: "
                f"{len(new_articles)}"
            )

            posted_count = 0

            for article in new_articles:

                if posted_count >= MAX_POSTS_PER_CHECK:

                    break

                success = await post_article(
                    bot,
                    article
                )

                # IMPORTANT:
                # Mark article as seen even when skipped
                # because it has no image.
                seen.add(
                    article["link"]
                )

                save_seen(
                    seen
                )

                if success:

                    posted_count += 1

                    await asyncio.sleep(
                        10
                    )

            print(
                f"\n✅ Posted this round: "
                f"{posted_count}"
            )

            print(
                "⏰ Waiting 30 minutes..."
            )

            await asyncio.sleep(
                CHECK_INTERVAL
            )

        except Exception as error:

            print(
                f"\n❌ MAIN LOOP ERROR: "
                f"{error}"
            )

            print(
                "🔄 Retrying in 60 seconds..."
            )

            await asyncio.sleep(
                60
            )


# =========================================================
# START
# =========================================================

if __name__ == "__main__":

    asyncio.run(
        main()
    )
