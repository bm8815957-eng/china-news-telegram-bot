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
# BOT SETTINGS
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")

CHANNEL_USERNAME = "@eHTDSNB"

CHECK_INTERVAL = 30 * 60  # 30 minutes

MAX_POSTS_PER_CHECK = 3

SEEN_FILE = "seen_news.json"


# =========================================================
# NEWS SOURCES
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
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,image/avif,"
        "image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# =========================================================
# LOAD SEEN ARTICLES
# =========================================================

def load_seen():

    try:

        with open(
            SEEN_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            return set(
                json.load(file)
            )

    except Exception:

        return set()


# =========================================================
# SAVE SEEN ARTICLES
# =========================================================

def save_seen(seen):

    # Keep database reasonably small
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
        str(text),
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
# CHINA NEWS FILTER
# =========================================================

def is_china_news(
    title,
    summary
):

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
# CONVERT IMAGE URL TO FULL URL
# =========================================================

def normalize_image_url(
    image_url,
    article_url
):

    if not image_url:
        return None

    image_url = str(
        image_url
    ).strip()

    # Example:
    # //www.chinadaily.com.cn/image.jpg

    if image_url.startswith("//"):

        return (
            "https:"
            + image_url
        )

    # Example:
    # /images/news.jpg

    if image_url.startswith("/"):

        return urljoin(
            article_url,
            image_url
        )

    # Example:
    # images/news.jpg

    if not image_url.startswith(
        (
            "http://",
            "https://"
        )
    ):

        return urljoin(
            article_url,
            image_url
        )

    return image_url


# =========================================================
# CHECK IF IMAGE URL LOOKS LIKE A LOGO/PLACEHOLDER
# =========================================================

def looks_like_bad_image(
    image_url
):

    lower = image_url.lower()

    blocked_words = [
        "logo",
        "logos",
        "favicon",
        "avatar",
        "icon",
        "icons",
        "placeholder",
        "default-image",
        "default_image",
        "defaultimage",
        "no-image",
        "no_image",
        "noimage",
        "loading",
        "spinner",
        "sprite",
        "qrcode",
        "qr-code",
        "wechat",
        "share",
    ]

    for word in blocked_words:

        if word in lower:

            return True

    return False


# =========================================================
# GET IMAGE URL FROM RSS ENTRY
# =========================================================

def get_rss_image_url(
    entry,
    article_url
):

    candidates = []

    # -----------------------------------------------------
    # media_content
    # -----------------------------------------------------

    media_content = entry.get(
        "media_content"
    )

    if media_content:

        for media in media_content:

            if isinstance(
                media,
                dict
            ):

                image_url = media.get(
                    "url"
                )

                if image_url:

                    candidates.append(
                        image_url
                    )

    # -----------------------------------------------------
    # media_thumbnail
    # -----------------------------------------------------

    media_thumbnail = entry.get(
        "media_thumbnail"
    )

    if media_thumbnail:

        for media in media_thumbnail:

            if isinstance(
                media,
                dict
            ):

                image_url = media.get(
                    "url"
                )

                if image_url:

                    candidates.append(
                        image_url
                    )

    # -----------------------------------------------------
    # Enclosures
    # -----------------------------------------------------

    enclosures = entry.get(
        "enclosures"
    )

    if enclosures:

        for enclosure in enclosures:

            if isinstance(
                enclosure,
                dict
            ):

                image_url = enclosure.get(
                    "href"
                ) or enclosure.get(
                    "url"
                )

                media_type = enclosure.get(
                    "type",
                    ""
                )

                if image_url:

                    if (
                        not media_type
                        or media_type.startswith(
                            "image/"
                        )
                    ):

                        candidates.append(
                            image_url
                        )

    # -----------------------------------------------------
    # Process candidates
    # -----------------------------------------------------

    for image_url in candidates:

        image_url = normalize_image_url(
            image_url,
            article_url
        )

        if not image_url:

            continue

        if looks_like_bad_image(
            image_url
        ):

            print(
                "⏭️ RSS image rejected:"
                f" {image_url}"
            )

            continue

        print(
            "🖼️ RSS image candidate:"
            f" {image_url}"
        )

        return image_url

    return None


# =========================================================
# GET IMAGE FROM ARTICLE OG TAGS
# =========================================================

def get_og_image_url(
    article_url
):

    try:

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

        # -------------------------------------------------
        # OpenGraph image
        # -------------------------------------------------

        og_images = soup.find_all(
            "meta",
            property="og:image"
        )

        for meta in og_images:

            image_url = meta.get(
                "content"
            )

            if not image_url:

                continue

            image_url = normalize_image_url(
                image_url,
                article_url
            )

            if not image_url:

                continue

            if looks_like_bad_image(
                image_url
            ):

                print(
                    "⏭️ OG image rejected:"
                    f" {image_url}"
                )

                continue

            print(
                "🖼️ OG image candidate:"
                f" {image_url}"
            )

            return image_url

        # -------------------------------------------------
        # Twitter image
        # -------------------------------------------------

        twitter_images = soup.find_all(
            "meta",
            attrs={
                "name": "twitter:image"
            }
        )

        for meta in twitter_images:

            image_url = meta.get(
                "content"
            )

            if not image_url:

                continue

            image_url = normalize_image_url(
                image_url,
                article_url
            )

            if not image_url:

                continue

            if looks_like_bad_image(
                image_url
            ):

                print(
                    "⏭️ Twitter image rejected:"
                    f" {image_url}"
                )

                continue

            print(
                "🖼️ Twitter image candidate:"
                f" {image_url}"
            )

            return image_url

    except Exception as error:

        print(
            "⚠️ Could not inspect article:"
            f" {error}"
        )

    return None


# =========================================================
# DOWNLOAD AND VERIFY IMAGE
# =========================================================

def download_and_verify_image(
    image_url
):

    try:

        print(
            "⬇️ Downloading image:"
            f" {image_url}"
        )

        response = requests.get(
            image_url,
            headers=HEADERS,
            timeout=25
        )

        response.raise_for_status()

        content_type = (
            response
            .headers
            .get(
                "content-type",
                ""
            )
            .lower()
        )

        image_data = response.content

        # -------------------------------------------------
        # Check Content-Type
        # -------------------------------------------------

        if not content_type.startswith(
            "image/"
        ):

            print(
                "⏭️ Rejected:"
                " server did not return an image."
            )

            return None

        # -------------------------------------------------
        # Reject very small files
        # -------------------------------------------------

        if len(image_data) < 10000:

            print(
                "⏭️ Rejected:"
                " image is too small."
            )

            return None

        # -------------------------------------------------
        # Check actual image signatures
        # -------------------------------------------------

        is_jpeg = (
            image_data[:3]
            == b"\xff\xd8\xff"
        )

        is_png = (
            image_data[:8]
            == b"\x89PNG\r\n\x1a\n"
        )

        is_gif = (
            image_data[:6]
            in (
                b"GIF87a",
                b"GIF89a"
            )
        )

        is_webp = (
            image_data[:4]
            == b"RIFF"
            and image_data[8:12]
            == b"WEBP"
        )

        if not (
            is_jpeg
            or is_png
            or is_gif
            or is_webp
        ):

            print(
                "⏭️ Rejected:"
                " file is not a recognized image."
            )

            return None

        print(
            "✅ Real image verified."
        )

        return image_data

    except Exception as error:

        print(
            "⚠️ Image download failed:"
            f" {error}"
        )

        return None


# =========================================================
# FIND REAL ARTICLE IMAGE
# =========================================================

def find_real_article_image(
    article
):

    article_url = article["link"]

    # -----------------------------------------------------
    # FIRST: RSS IMAGE
    # -----------------------------------------------------

    rss_image = get_rss_image_url(
        article.get(
            "entry",
            {}
        ),
        article_url
    )

    if rss_image:

        image_data = download_and_verify_image(
            rss_image
        )

        if image_data:

            return image_data

    # -----------------------------------------------------
    # SECOND: OG IMAGE
    # -----------------------------------------------------

    og_image = get_og_image_url(
        article_url
    )

    if og_image:

        image_data = download_and_verify_image(
            og_image
        )

        if image_data:

            return image_data

    # -----------------------------------------------------
    # IMPORTANT:
    #
    # We DO NOT scan random <img> tags.
    #
    # This prevents the China Daily logo,
    # X placeholders and other webpage graphics
    # from being used as news photos.
    # -----------------------------------------------------

    print(
        "❌ No trusted article image found."
    )

    return None


# =========================================================
# CREATE TELEGRAM CAPTION
# =========================================================

def make_caption(
    article
):

    title = clean_text(
        article["title"]
    )

    summary = clean_text(
        article["summary"]
    )

    # Limit summary length
    if len(summary) > 500:

        summary = (
            summary[:500]
            .rsplit(
                " ",
                1
            )[0]
            + "..."
        )

    # If no summary exists
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
# GET NEWS
# =========================================================

def get_news():

    articles = []

    for feed_url in RSS_FEEDS:

        try:

            print(
                f"📡 Reading:"
                f" {feed_url}"
            )

            feed = feedparser.parse(
                feed_url
            )

            print(
                f"📥 Feed entries:"
                f" {len(feed.entries)}"
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
                        "⏭️ Skipping non-China:"
                        f" {title}"
                    )

                    continue

                articles.append(
                    {
                        "title": title,
                        "link": link,
                        "summary": summary,
                        "entry": entry,
                    }
                )

        except Exception as error:

            print(
                "❌ RSS error:"
                f" {error}"
            )

    return articles


# =========================================================
# POST ARTICLE
# =========================================================

async def post_article(
    bot,
    article
):

    print(
        "\n"
        "========================================"
    )

    print(
        f"📰 {article['title']}"
    )

    print(
        "========================================"
    )

    # Image is REQUIRED
    image_data = find_real_article_image(
        article
    )

    if not image_data:

        print(
            "⏭️ SKIPPED:"
            " no genuine news image."
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
            "✅ POSTED WITH REAL IMAGE!"
        )

        return True

    except Exception as error:

        print(
            "❌ Telegram error:"
            f" {error}"
        )

        return False


# =========================================================
# MAIN BOT
# =========================================================

async def main():

    if not BOT_TOKEN:

        raise ValueError(
            "BOT_TOKEN is missing."
            " Add BOT_TOKEN in Railway Variables."
        )

    bot = Bot(
        token=BOT_TOKEN
    )

    seen = load_seen()

    print(
        "========================================"
    )

    print(
        "🤖 CHINA NEWS BOT V3"
    )

    print(
        "========================================"
    )

    print(
        f"📢 Channel:"
        f" {CHANNEL_USERNAME}"
    )

    print(
        "🇨🇳 China-only: ON"
    )

    print(
        "🖼️ Real-image-only: ON"
    )

    print(
        "🚫 Random webpage images: OFF"
    )

    print(
        "🚫 Logo/placeholder images: OFF"
    )

    print(
        "🔄 Duplicate protection: ON"
    )

    print(
        "⏰ Checking every 30 minutes"
    )

    print(
        "========================================"
    )

    while True:

        try:

            print(
                "\n🔄 Checking for news..."
            )

            articles = get_news()

            print(
                f"🇨🇳 China articles found:"
                f" {len(articles)}"
            )

            new_articles = []

            for article in articles:

                article_id = article["link"]

                if article_id in seen:

                    print(
                        f"♻️ Already processed:"
                        f" {article['title']}"
                    )

                    continue

                new_articles.append(
                    article
                )

            print(
                f"🆕 New articles:"
                f" {len(new_articles)}"
            )

            posted = 0

            for article in new_articles:

                if posted >= MAX_POSTS_PER_CHECK:

                    break

                success = await post_article(
                    bot,
                    article
                )

                # Only mark it as seen after
                # a successful post.
                #
                # This means articles without an
                # image can be retried later if
                # the source adds an image.
                if success:

                    seen.add(
                        article["link"]
                    )

                    save_seen(
                        seen
                    )

                    posted += 1

                    await asyncio.sleep(
                        10
                    )

            print(
                f"\n📢 Posted this round:"
                f" {posted}"
            )

            print(
                "⏰ Waiting 30 minutes..."
            )

            await asyncio.sleep(
                CHECK_INTERVAL
            )

        except Exception as error:

            print(
                "\n❌ Main loop error:"
                f" {error}"
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
