import os
import asyncio
from telegram import Bot

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_USERNAME = "@eHTDSNB"


async def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN is not set")

    bot = Bot(token=BOT_TOKEN)

    message = (
        "🇨🇳 创亿绘图大师\n\n"
        "🤖 新闻机器人测试成功！\n\n"
        "这个频道的自动新闻系统正在准备中。"
    )

    await bot.send_message(
        chat_id=CHANNEL_USERNAME,
        text=message
    )

    print("✅ Test message sent successfully!")


if __name__ == "__main__":
    asyncio.run(main())
