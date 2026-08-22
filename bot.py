import os
import asyncio
import json
import re
import html
from urllib.parse import urljoin

import requests
import feedparser
from bs4 import BeautifulSoup

from telegram import (
    Bot,
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from telegram.constants import ChatMemberStatus
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)


# =========================================================
# SETTINGS
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")

CHANNEL_USERNAME = "@eHTDSNB"

CHANNEL_LINK = "https://t.me/eHTDSNB"

CHECK_INTERVAL = 30 * 60

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
    "Accept-Language": "en-US,en;q=0.9",
}


# =========================================================
# START MESSAGE
# =========================================================

def join_keyboard():

    keyboard = [
        [
            InlineKeyboardButton(
                "🇨🇳 加入频道 / Join Channel",
                url=CHANNEL_LINK
            )
        ],
        [
            InlineKeyboardButton(
                "✅ 我已加入 / I've Joined",
                callback_data="check_join"
            )
        ],
    ]

    return InlineKeyboardMarkup(
        keyboard
    )


async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user

    if not user:
        return

    joined = await check_membership(
        context.bot,
        user.id
    )

    if joined:

        await update.message.reply_text(
            "🎉 欢迎来到创亿绘图大师！\n\n"
            "🇨🇳 您已经成功加入频道。\n\n"
            "📰 您现在可以使用机器人了。\n\n"
            "感谢您的关注！"
        )

        return

    await update.message.reply_text(
        "👋 欢迎！\n\n"
        "🇨🇳 欢迎来到「创亿绘图大师」\n\n"
        "📢 使用机器人之前，请先加入我们的频道。\n\n"
        "加入频道后，点击下面的：\n"
        "✅「我已加入」\n\n"
        "然后机器人会验证您的频道状态。",
        reply_markup=join_keyboard()
    )


# =========================================================
# CHECK CHANNEL MEMBERSHIP
# =========================================================

async def check_membership(
    bot,
    user_id
):

    try:

        member = await bot.get_chat_member(
            chat_id=CHANNEL_USERNAME,
            user_id=user_id
        )

        return member.status in [
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER,
        ]

    except Exception as error:

        print(
            f"⚠️ Membership check error: {error}"
        )

        return False


# =========================================================
# CHECK JOIN BUTTON
# =========================================================

async def check_join_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    user = query.from_user

    joined = await check_membership(
        context.bot,
        user.id
    )

    if joined:

        await query.edit_message_text(
            "🎉 验证成功！\n\n"
            "🇨🇳 您已经加入「创亿绘图大师」。\n\n"
            "✅ 欢迎使用我们的机器人！\n\n"
            "📰 您将获得最新的中国资讯。"
        )

    else:

        await query.edit_message_text(
            "❌ 还没有检测到您加入频道。\n\n"
            "请先点击下面的按钮加入：",
            reply_markup=join_keyboard()
        )


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

    text = html.unescape(
        text
    )

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
# NORMALIZE IMAGE URL
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

    if image_url.startswith("//"):

        return (
            "https:"
            + image_url
        )

    if image_url.startswith("/"):

        return urljoin(
            article_url,
            image_url
        )

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
# REJECT BAD IMAGES
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
# RSS IMAGE
# =========================================================

def get_rss_image_url(
    entry,
    article_url
):

    candidates = []

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

    enclosures = entry.get(
        "enclosures"
    )

    if enclosures:

        for enclosure in enclosures:

            if isinstance(
                enclosure,
                dict
            ):

                image_url = (
                    enclosure.get("href")
                    or enclosure.get("url")
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
            continue

        return image_url

    return None


# =========================================================
# ARTICLE OG IMAGE
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

        # OpenGraph
        for meta in soup.find_all(
            "meta",
            property="og:image"
        ):

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
                continue

            return image_url

        # Twitter image
        for meta in soup.find_all(
            "meta",
            attrs={
                "name": "twitter:image"
            }
        ):

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
                continue

            return image_url

    except Exception as error:

        print(
            f"⚠️ Article image error: {error}"
        )

    return None


# =========================================================
# DOWNLOAD AND VERIFY IMAGE
# =========================================================

def download_image(
    image_url
):

    try:

        response = requests.get(
            image_url,
            headers=HEADERS,
            timeout=25
        )

        response.raise_for_status()

        content_type = (
            response.headers
            .get(
                "content-type",
                ""
            )
            .lower()
        )

        image_data = response.content

        if not content_type.startswith(
            "image/"
        ):

            return None

        if len(image_data) < 10000:

            return None

        jpeg = (
            image_data[:3]
            == b"\xff\xd8\xff"
        )

        png = (
            image_data[:8]
            == b"\x89PNG\r\n\x1a\n"
        )

        gif = (
            image_data[:6]
            in (
                b"GIF87a",
                b"GIF89a"
            )
        )

        webp = (
            image_data[:4]
            == b"RIFF"
            and image_data[8:12]
            == b"WEBP"
        )

        if not (
            jpeg
            or png
            or gif
            or webp
        ):

            return None

        return image_data

    except Exception as error:

        print(
            f"⚠️ Image download error: {error}"
        )

        return None


# =========================================================
# FIND REAL NEWS IMAGE
# =========================================================

def find_article_image(
    article
):

    article_url = article["link"]

    # RSS image first
    rss_image = get_rss_image_url(
        article.get(
            "entry",
            {}
        ),
        article_url
    )

    if rss_image:

        image_data = download_image(
            rss_image
        )

        if image_data:

            print(
                "✅ Real RSS image found."
            )

            return image_data

    # OG image second
    og_image = get_og_image_url(
        article_url
    )

    if og_image:

        image_data = download_image(
            og_image
        )

        if image_data:

            print(
                "✅ Real article image found."
            )

            return image_data

    print(
        "❌ No genuine article image."
    )

    return None


# =========================================================
# CREATE NEWS CAPTION
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

    if len(summary) > 500:

        summary = (
            summary[:500]
            .rsplit(
                " ",
                1
            )[0]
            + "..."
        )

    if not summary:

        summary = (
            "中国最新消息受到关注，"
            "相关情况正在持续发展。"
        )

    return (
        "🇨🇳 <b>中国新闻</b>\n\n"
        f"📰 <b>{html.escape(title)}</b>\n\n"
        f"{html.escape(summary)}\n\n"
        "━━━━━━━━━━━━━━\n"
        "🔗 <a href=\""
        f"{html.escape(article['link'])}"
        "\">阅读原文</a>\n\n"
        "#中国新闻 #中国 #ChinaNews"
    )


# =========================================================
# GET NEWS
# =========================================================

def get_news():

    articles = []

    for feed_url in RSS_FEEDS:

        try:

            feed = feedparser.parse(
                feed_url
            )

            print(
                f"📥 Feed articles: "
                f"{len(feed.entries)}"
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
                f"❌ RSS error: {error}"
            )

    return articles


# =========================================================
# POST NEWS
# =========================================================

async def post_article(
    bot,
    article
):

    print(
        f"📰 Checking: "
        f"{article['title']}"
    )

    image_data = find_article_image(
        article
    )

    # Image is mandatory
    if not image_data:

        print(
            "⏭️ Skipped — no genuine image."
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
            "✅ News posted with image!"
        )

        return True

    except Exception as error:

        print(
            f"❌ Telegram posting error: "
            f"{error}"
        )

        return False


# =========================================================
# NEWS LOOP
# =========================================================

async def news_loop(
    bot
):

    seen = load_seen()

    print(
        "📰 News system started."
    )

    while True:

        try:

            articles = get_news()

            print(
                f"🇨🇳 China news found: "
                f"{len(articles)}"
            )

            new_articles = []

            for article in articles:

                if article["link"] not in seen:

                    new_articles.append(
                        article
                    )

            posted = 0

            for article in new_articles:

                if posted >= MAX_POSTS_PER_CHECK:
                    break

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

                    posted += 1

                    await asyncio.sleep(
                        10
                    )

            print(
                f"📢 Posted this round: "
                f"{posted}"
            )

            print(
                "⏰ Next check in 30 minutes."
            )

            await asyncio.sleep(
                CHECK_INTERVAL
            )

        except Exception as error:

            print(
                f"❌ News loop error: "
                f"{error}"
            )

            await asyncio.sleep(
                60
            )


# =========================================================
# MAIN
# =========================================================

async def main():

    if not BOT_TOKEN:

        raise ValueError(
            "BOT_TOKEN is missing."
        )

    # Create Telegram application
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    # /start
    application.add_handler(
        CommandHandler(
            "start",
            start_command
        )
    )

    # "I've Joined" button
    application.add_handler(
        CallbackQueryHandler(
            check_join_callback,
            pattern="^check_join$"
        )
    )

    # Initialize
    await application.initialize()

    # Start application
    await application.start()

    # Start polling
    await application.updater.start_polling()

    print(
        "======================================"
    )

    print(
        "🤖 CHINA NEWS BOT"
    )

    print(
        "======================================"
    )

    print(
        f"📢 Channel: {CHANNEL_USERNAME}"
    )

    print(
        "🇨🇳 China news: ON"
    )

    print(
        "🖼️ Real images only: ON"
    )

    print(
        "👥 Join requirement: ON"
    )

    print(
        "🚫 Logos/placeholders: OFF"
    )

    print(
        "======================================"
    )

    # Start automatic news system
    news_task = asyncio.create_task(
        news_loop(
            application.bot
        )
    )

    try:

        # Keep everything running
        await asyncio.Event().wait()

    finally:

        news_task.cancel()

        await application.updater.stop()

        await application.stop()

        await application.shutdown()


# =========================================================
# START BOT
# =========================================================

if __name__ == "__main__":

    asyncio.run(
        main()
    )
