import asyncio
import logging

from pyrogram import Client, filters

from config import API_ID, API_HASH, BOT_TOKEN


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger(__name__)


app = Client(
    name="contentprox",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True
)


@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message):

    logger.info(
        "START RECEIVED | user_id=%s",
        message.from_user.id
    )

    await message.reply_text(
        "✅ ContentProXBot is working!"
    )


@app.on_message(filters.private)
async def message_debug(client, message):

    logger.info(
        "MESSAGE RECEIVED | text=%s | user_id=%s",
        message.text,
        message.from_user.id
    )

    if not (
        message.text
        and message.text.startswith("/start")
    ):
        await message.reply_text(
            "📩 Message received successfully!"
        )


async def main():

    logger.info("STARTING BOT...")

    await app.start()

    me = await app.get_me()

    logger.info(
        "RUNNING AS: @%s | BOT ID: %s",
        me.username,
        me.id
    )

    logger.info("BOT IS READY AND WAITING FOR UPDATES.")

    await asyncio.Event().wait()


if __name__ == "__main__":

    asyncio.run(main())
