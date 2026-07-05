from functools import wraps

from telegram import Update
from telegram.ext import ContextTypes

from . import database as db


def allowed_only(func):
    """Restricts a handler to any user on the allowlist (owner + added users)."""

    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        if user is None or not db.is_allowed(user.id):
            if update.effective_message:
                await update.effective_message.reply_text(
                    f"This bot is private. Your Telegram ID is `{user.id if user else 'unknown'}` "
                    "— ask the owner to run /adduser with that number to grant you access.",
                    parse_mode="Markdown",
                )
            return
        return await func(update, context, *args, **kwargs)

    return wrapper


def owner_only(func):
    """Restricts a handler to the bootstrap owner only (user management commands)."""

    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        if user is None or not db.is_owner(user.id):
            if update.effective_message:
                await update.effective_message.reply_text("Only the bot owner can do that.")
            return
        return await func(update, context, *args, **kwargs)

    return wrapper
