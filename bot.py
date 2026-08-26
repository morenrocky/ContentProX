import asyncio
import logging

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import BOT_TOKEN, API_ID, API_HASH, ADMIN_IDS
from database import users, access_requests


# ==================== LOGGING ====================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger(__name__)


# ==================== BOT ====================

app = Client(
    name="ContentProXBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True
)


# ==================== KEYBOARDS ====================

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


# ==================== DATABASE ====================

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
        "referral_count": 0,
        "referral_rewarded": False
    }

    await users.insert_one(new_user)

    logger.info(
        "NEW USER CREATED | user_id=%s",
        tg_user.id
    )

    return new_user


async def unlock_user(user_id):

    await users.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "is_unlocked": True
            }
        }
    )

    logger.info(
        "USER UNLOCKED | user_id=%s",
        user_id
    )


# ==================== ACCESS SCREENS ====================

async def show_locked(client, chat_id, user_id):

    user = await users.find_one(
        {"user_id": user_id}
    )

    referrals = user.get(
        "referral_count",
        0
    )

    await client.send_message(
        chat_id,
        "🔒 <b>Access Locked</b>\n\n"
        "👥 Invite <b>1 new user</b> to unlock access.\n\n"
        f"📊 Progress: <b>{referrals}/1</b>\n\n"
        "Or request manual admin approval.",
        reply_markup=locked_keyboard(user_id)
    )


async def show_main_menu(message):

    await message.reply_text(
        "🔓 <b>Welcome to ContentProX!</b>\n\n"
        "Your access is active.",
        reply_markup=main_keyboard()
    )

# ===================== Temp Debug Line =================
@app.on_raw_update()
async def raw_update_debug(client, update, users, chats):
    logger.info(
        "RAW UPDATE RECEIVED | %s",
        type(update).__name__
    )

# ==================== START COMMAND ====================

@app.on_message(
    filters.command("start") & filters.private
)
async def start_command(client, message):

    logger.info(
        "START RECEIVED | user=%s | text=%s | command=%s",
        message.from_user.id if message.from_user else None,
        message.text,
        message.command
    )

    tg_user = message.from_user

    if not tg_user:
        return

    try:

        user = await get_or_create_user(
            tg_user
        )

        # ---------- HANDLE REFERRAL ----------

        if len(message.command) > 1:

            parameter = message.command[1]

            if parameter.startswith("ref_"):

                try:
                    referrer_id = int(
                        parameter.replace(
                            "ref_",
                            ""
                        )
                    )
                except ValueError:
                    referrer_id = None

                if (
                    referrer_id
                    and referrer_id != tg_user.id
                    and user.get("referred_by") is None
                ):

                    referrer = await users.find_one(
                        {
                            "user_id": referrer_id
                        }
                    )

                    if referrer:

                        await users.update_one(
                            {
                                "user_id": tg_user.id
                            },
                            {
                                "$set": {
                                    "referred_by": referrer_id
                                }
                            }
                        )

                        user = await users.find_one(
                            {
                                "user_id": tg_user.id
                            }
                        )

                        logger.info(
                            "REFERRAL LINKED | new_user=%s | referrer=%s",
                            tg_user.id,
                            referrer_id
                        )

        # ---------- BAN CHECK ----------

        if user.get("is_banned"):

            await message.reply_text(
                "🚫 You are not allowed to use this bot."
            )

            return

        # ---------- ALREADY UNLOCKED ----------

        if user.get("is_unlocked"):

            await show_main_menu(
                message
            )

            return

        # ---------- AGE CONFIRMATION ----------

        if not user.get(
            "is_adult_confirmed"
        ):

            await message.reply_text(
                "🔞 <b>Age Confirmation Required</b>\n\n"
                "This bot is intended only for users aged "
                "18 or above.\n\n"
                "Please confirm your age to continue.",
                reply_markup=age_keyboard()
            )

            return

        # ---------- LOCKED ----------

        await show_locked(
            client,
            message.chat.id,
            tg_user.id
        )

    except Exception:

        logger.exception(
            "ERROR IN START HANDLER"
        )

        await message.reply_text(
            "❌ Something went wrong. Please try again later."
        )


# ==================== CALLBACKS ====================

@app.on_callback_query()
async def callbacks(client, callback):

    data = callback.data
    user_id = callback.from_user.id

    logger.info(
        "CALLBACK RECEIVED | user=%s | data=%s",
        user_id,
        data
    )

    try:

        user = await users.find_one(
            {
                "user_id": user_id
            }
        )

        if not user:

            await callback.answer(
                "Please restart the bot.",
                show_alert=True
            )

            return

        # ==================================================
        # ADULT CONFIRMATION
        # ==================================================

        if data == "confirm_adult":

            # Atomically confirm only once
            result = await users.update_one(
                {
                    "user_id": user_id,
                    "is_adult_confirmed": False
                },
                {
                    "$set": {
                        "is_adult_confirmed": True
                    }
                }
            )

            user = await users.find_one(
                {
                    "user_id": user_id
                }
            )

            referrer_id = user.get(
                "referred_by"
            )

            # Credit referral only once
            if (
                referrer_id
                and not user.get(
                    "referral_rewarded",
                    False
                )
            ):

                reward_result = await users.update_one(
                    {
                        "user_id": user_id,
                        "referral_rewarded": False
                    },
                    {
                        "$set": {
                            "referral_rewarded": True
                        }
                    }
                )

                if reward_result.modified_count:

                    await users.update_one(
                        {
                            "user_id": referrer_id
                        },
                        {
                            "$inc": {
                                "referral_count": 1
                            }
                        }
                    )

                    referrer = await users.find_one(
                        {
                            "user_id": referrer_id
                        }
                    )

                    logger.info(
                        "REFERRAL CREDITED | referrer=%s | count=%s",
                        referrer_id,
                        referrer.get(
                            "referral_count",
                            0
                        )
                    )

                    # Unlock referrer after 1 referral
                    if referrer.get(
                        "referral_count",
                        0
                    ) >= 1:

                        await unlock_user(
                            referrer_id
                        )

                        try:

                            await client.send_message(
                                referrer_id,
                                "🎉 <b>Access Unlocked!</b>\n\n"
                                "Your referral requirement has "
                                "been completed.",
                                reply_markup=main_keyboard()
                            )

                        except Exception:

                            logger.exception(
                                "COULD NOT NOTIFY REFERRER | user_id=%s",
                                referrer_id
                            )

            # Get fresh referral progress
            user = await users.find_one(
                {
                    "user_id": user_id
                }
            )

            referrals = user.get(
                "referral_count",
                0
            )

            await callback.message.edit_text(
                "🔒 <b>Access Locked</b>\n\n"
                "👥 Invite <b>1 new user</b> to unlock access.\n\n"
                f"📊 Progress: <b>{referrals}/1</b>\n\n"
                "Or request manual admin approval.",
                reply_markup=locked_keyboard(user_id)
            )

            await callback.answer(
                "Age confirmed."
            )

        # ==================================================
        # UNDERAGE
        # ==================================================

        elif data == "underage":

            await callback.message.edit_text(
                "🚫 Sorry, this bot is only available "
                "to users aged 18 or above."
            )

            await callback.answer()

        # ==================================================
        # ADMIN APPROVAL REQUEST
        # ==================================================

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

            sent_to_admin = False

            for admin_id in ADMIN_IDS:

                try:

                    await client.send_message(
                        admin_id,
                        text,
                        reply_markup=admin_keyboard
                    )

                    sent_to_admin = True

                except Exception:

                    logger.exception(
                        "COULD NOT SEND APPROVAL REQUEST | admin=%s",
                        admin_id
                    )

            if sent_to_admin:

                await callback.answer(
                    "Your request has been sent for approval.",
                    show_alert=True
                )

            else:

                await callback.answer(
                    "❌ Could not contact the admin.",
                    show_alert=True
                )

        # ==================================================
        # ADMIN APPROVE
        # ==================================================

        elif data.startswith("approve_"):

            if user_id not in ADMIN_IDS:

                await callback.answer(
                    "Unauthorized.",
                    show_alert=True
                )

                return

            target_id = int(
                data.replace(
                    "approve_",
                    ""
                )
            )

            await unlock_user(
                target_id
            )

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

            except Exception:

                logger.exception(
                    "COULD NOT NOTIFY APPROVED USER | user=%s",
                    target_id
                )

            await callback.answer(
                "User approved."
            )

        # ==================================================
        # ADMIN REJECT
        # ==================================================

        elif data.startswith("reject_"):

            if user_id not in ADMIN_IDS:

                await callback.answer(
                    "Unauthorized.",
                    show_alert=True
                )

                return

            target_id = int(
                data.replace(
                    "reject_",
                    ""
                )
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

        # ==================================================
        # CHECK ACCESS
        # ==================================================

        elif data == "check_access":

            user = await users.find_one(
                {
                    "user_id": user_id
                }
            )

            if user and user.get(
                "is_unlocked"
            ):

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

        # ==================================================
        # UNIMPLEMENTED BUTTONS
        # ==================================================

        elif data in [
            "search",
            "browse",
            "profile"
        ]:

            await callback.answer(
                "🚧 This feature is coming soon!",
                show_alert=True
            )

    except Exception:

        logger.exception(
            "ERROR IN CALLBACK HANDLER | data=%s | user=%s",
            data,
            user_id
        )

        try:

            await callback.answer(
                "❌ Something went wrong.",
                show_alert=True
            )

        except Exception:
            pass


# ==================== MAIN ====================

async def main():

    logger.info(
        "STARTING CONTENTPROXBOT..."
    )

    await app.start()

    me = await app.get_me()

    logger.info(
        "RUNNING AS: @%s | BOT ID: %s",
        me.username,
        me.id
    )

    logger.info(
        "ContentProXBot started successfully."
    )

    await asyncio.Event().wait()


if __name__ == "__main__":

    try:

        asyncio.run(
            main()
        )

    except KeyboardInterrupt:

        logger.info(
            "ContentProXBot stopped."
    )
