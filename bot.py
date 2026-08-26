import asyncio
import logging

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import BOT_TOKEN, API_ID, API_HASH, ADMIN_IDS
from database import users, access_requests


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger(__name__)


app = Client(
    "ContentProXBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)


def age_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🔞 I am 18+",
                callback_data="confirm_adult"
            )
        ],
        [
            InlineKeyboardButton(
                "❌ I am under 18",
                callback_data="underage"
            )
        ]
    ])


def locked_keyboard(user_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "👥 Invite 1 User",
                url=f"https://t.me/ContentProXbot?start=ref_{user_id}"
            )
        ],
        [
            InlineKeyboardButton(
                "👑 Request Admin Approval",
                callback_data="request_approval"
            )
        ],
        [
            InlineKeyboardButton(
                "🔄 Check Access",
                callback_data="check_access"
            )
        ]
    ])


def main_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🔎 Search",
                callback_data="search"
            ),
            InlineKeyboardButton(
                "📁 Browse",
                callback_data="browse"
            )
        ],
        [
            InlineKeyboardButton(
                "👤 My Profile",
                callback_data="profile"
            )
        ]
    ])


async def get_or_create_user(tg_user):
    user = await users.find_one(
        {"user_id": tg_user.id}
    )

    if user:
        return user

    new_user = {
        "user_id": tg_user.id,
        "first_name": tg_user.first_name,
        "username": tg_user.username,
        "is_adult_confirmed": False,
        "is_unlocked": False,
        "is_banned": False,
        "referred_by": None,
        "referral_count": 0
    }

    await users.insert_one(new_user)

    return new_user


async def show_locked(client, chat_id, user_id):
    user = await users.find_one(
        {"user_id": user_id}
    )

    referrals = user.get("referral_count", 0)

    await client.send_message(
        chat_id,
        f"🔒 <b>Access Locked</b>\n\n"
        f"👥 Invite <b>1 new user</b> to unlock access.\n\n"
        f"📊 Progress: <b>{referrals}/1</b>\n\n"
        f"Or request manual admin approval.",
        reply_markup=locked_keyboard(user_id)
    )


async def unlock_user(user_id):
    await users.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "is_unlocked": True
            }
        }
    )


@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message):

    tg_user = message.from_user

    if not tg_user:
        return

    user = await get_or_create_user(tg_user)

    # Handle referral parameter
    if len(message.command) > 1:
        parameter = message.command[1]

        if parameter.startswith("ref_"):

            try:
                referrer_id = int(
                    parameter.replace("ref_", "")
                )
            except ValueError:
                referrer_id = None

            if (
                referrer_id
                and referrer_id != tg_user.id
                and user.get("referred_by") is None
            ):

                referrer = await users.find_one(
                    {"user_id": referrer_id}
                )

                if referrer:

                    await users.update_one(
                        {"user_id": tg_user.id},
                        {
                            "$set": {
                                "referred_by": referrer_id
                            }
                        }
                    )

                    user = await users.find_one(
                        {"user_id": tg_user.id}
                    )

    # Ban check
    if user.get("is_banned"):
        await message.reply_text(
            "🚫 You are not allowed to use this bot."
        )
        return

    # Already unlocked
    if user.get("is_unlocked"):
        await message.reply_text(
            "🔓 <b>Welcome back!</b>\n\n"
            "You have access to ContentProX.",
            reply_markup=main_keyboard()
        )
        return

    # Adult confirmation
    if not user.get("is_adult_confirmed"):

        await message.reply_text(
            "🔞 <b>Age Confirmation Required</b>\n\n"
            "This bot is intended only for users aged 18 or above.\n\n"
            "Please confirm your age to continue.",
            reply_markup=age_keyboard()
        )
        return

    await show_locked(
        client,
        message.chat.id,
        tg_user.id
    )


@app.on_callback_query()
async def callbacks(client, callback):

    data = callback.data
    user_id = callback.from_user.id

    user = await users.find_one(
        {"user_id": user_id}
    )

    if not user:
        await callback.answer(
            "Please restart the bot.",
            show_alert=True
        )
        return

    # Adult confirmation
    if data == "confirm_adult":

        await users.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "is_adult_confirmed": True
                }
            }
        )

        # Count referral if this user was referred
        user = await users.find_one(
            {"user_id": user_id}
        )

        referrer_id = user.get("referred_by")

        if referrer_id:

            referrer = await users.find_one(
                {"user_id": referrer_id}
            )

            if referrer:

                new_count = (
                    referrer.get("referral_count", 0)
                    + 1
                )

                await users.update_one(
                    {"user_id": referrer_id},
                    {
                        "$set": {
                            "referral_count": new_count
                        }
                    }
                )

                # Unlock after 1 referral
                if new_count >= 1:

                    await unlock_user(
                        referrer_id
                    )

                    try:
                        await client.send_message(
                            referrer_id,
                            "🎉 <b>Access Unlocked!</b>\n\n"
                            "Your referral requirement has been completed.",
                            reply_markup=main_keyboard()
                        )
                    except Exception as e:
                        logger.warning(
                            f"Could not notify {referrer_id}: {e}"
                        )

        await callback.message.edit_text(
            "🔒 <b>Access Locked</b>\n\n"
            "👥 Invite <b>1 new user</b> to unlock access.\n\n"
            "📊 Progress: <b>0/1</b>\n\n"
            "Or request manual admin approval.",
            reply_markup=locked_keyboard(user_id)
        )

        await callback.answer(
            "Age confirmed."
        )

    elif data == "underage":

        await callback.message.edit_text(
            "🚫 Sorry, this bot is only available "
            "to users aged 18 or above."
        )

        await callback.answer()

    # Request admin approval
    elif data == "request_approval":

        existing = await access_requests.find_one(
            {
                "user_id": user_id,
                "status": "pending"
            }
        )

        if existing:

            await callback.answer(
                "Your request is already pending.",
                show_alert=True
            )

            return

        request = {
            "user_id": user_id,
            "status": "pending"
        }

        await access_requests.insert_one(
            request
        )

        username = callback.from_user.username

        text = (
            "🔔 <b>New Access Request</b>\n\n"
            f"👤 Name: {callback.from_user.first_name}\n"
            f"🆔 ID: <code>{user_id}</code>\n"
            f"🔗 Username: "
            f"{'@' + username if username else 'None'}\n\n"
            f"👥 Referrals: "
            f"{user.get('referral_count', 0)}/1"
        )

        admin_keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🔓 Approve",
                    callback_data=f"approve_{user_id}"
                ),
                InlineKeyboardButton(
                    "❌ Reject",
                    callback_data=f"reject_{user_id}"
                )
            ]
        ])

        for admin_id in ADMIN_IDS:

            try:

                await client.send_message(
                    admin_id,
                    text,
                    reply_markup=admin_keyboard
                )

            except Exception as e:

                logger.error(
                    f"Could not send request to admin "
                    f"{admin_id}: {e}"
                )

        await callback.answer(
            "Your request has been sent to the admin.",
            show_alert=True
        )

    # Admin approval
    elif data.startswith("approve_"):

        if user_id not in ADMIN_IDS:

            await callback.answer(
                "Unauthorized.",
                show_alert=True
            )

            return

        target_id = int(
            data.replace("approve_", "")
        )

        await unlock_user(target_id)

        await access_requests.update_many(
            {
                "user_id": target_id,
                "status": "pending"
            },
            {
                "$set": {
                    "status": "approved"
                }
            }
        )

        await callback.message.edit_text(
            f"✅ User <code>{target_id}</code> approved."
        )

        try:

            await client.send_message(
                target_id,
                "🎉 <b>Your access has been approved!</b>\n\n"
                "You can now use ContentProX.",
                reply_markup=main_keyboard()
            )

        except Exception as e:

            logger.warning(
                f"Could not notify user {target_id}: {e}"
            )

        await callback.answer(
            "User approved."
        )

    # Admin rejection
    elif data.startswith("reject_"):

        if user_id not in ADMIN_IDS:

            await callback.answer(
                "Unauthorized.",
                show_alert=True
            )

            return

        target_id = int(
            data.replace("reject_", "")
        )

        await access_requests.update_many(
            {
                "user_id": target_id,
                "status": "pending"
            },
            {
                "$set": {
                    "status": "rejected"
                }
            }
        )

        await callback.message.edit_text(
            f"❌ User <code>{target_id}</code> rejected."
        )

        await callback.answer(
            "Request rejected."
        )

    # Check access
    elif data == "check_access":

        user = await users.find_one(
            {"user_id": user_id}
        )

        if user.get("is_unlocked"):

            await callback.message.edit_text(
                "🔓 <b>Access Granted!</b>\n\n"
                "Welcome to ContentProX.",
                reply_markup=main_keyboard()
            )

        else:

            await callback.answer(
                "🔒 You have not unlocked access yet.",
                show_alert=True
            )


async def main():

    await app.start()

    logger.info(
        "ContentProXBot started successfully."
    )

    await asyncio.Event().wait()


if __name__ == "__main__":

    asyncio.run(main())
