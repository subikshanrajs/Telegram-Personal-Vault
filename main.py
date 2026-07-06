import logging

from telegram.ext import (
    AIORateLimiter,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from bot.config import BOT_TOKEN, LOCAL_API_URL
from bot import database as db
from bot import handlers as h

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)


def main():
    db.init_db()
    builder = ApplicationBuilder().token(BOT_TOKEN).rate_limiter(
        # Telegram allows bursts but recommends against exceeding ~1 msg/sec overall
        # and ~20/min to the same group or channel. Bulk uploads hammer the private
        # channel with copy_message calls, so this throttles and auto-retries on
        # Telegram's own RetryAfter responses instead of silently dropping files.
        AIORateLimiter(
            overall_max_rate=30,
            overall_time_period=1,
            group_max_rate=18,
            group_time_period=60,
            max_retries=5,
        )
    )

    if LOCAL_API_URL:
        builder = (
            builder.base_url(f"{LOCAL_API_URL}/bot")
            .base_file_url(f"{LOCAL_API_URL}/file/bot")
            .local_mode(True)
            .read_timeout(120)
            .write_timeout(120)
            .connect_timeout(30)
            .pool_timeout(30)
        )
        logging.info("Using local Bot API server at %s", LOCAL_API_URL)

    app = builder.build()

    app.add_handler(CommandHandler("start", h.start))
    app.add_handler(CommandHandler("help", h.start))
    app.add_handler(CommandHandler("menu", h.show_menu))
    app.add_handler(CommandHandler("whoami", h.whoami))

    app.add_handler(CommandHandler("list", h.list_files))
    app.add_handler(CommandHandler("uncollected", h.uncollected_cmd))
    app.add_handler(CommandHandler("search", h.search))
    app.add_handler(CommandHandler("collections", h.collections_cmd))
    app.add_handler(CommandHandler("collection", h.set_collection_cmd))
    app.add_handler(CommandHandler("bulkcollection", h.bulkcollection_cmd))
    app.add_handler(CommandHandler("mergecollections", h.mergecollections_cmd))
    app.add_handler(CommandHandler("renamecollection", h.renamecollection_cmd))
    app.add_handler(CommandHandler("regroup", h.regroup_cmd))
    app.add_handler(CommandHandler("duplicates", h.duplicates_cmd))
    app.add_handler(CommandHandler("rename", h.rename))
    app.add_handler(CommandHandler("delete", h.delete))
    app.add_handler(CommandHandler("stats", h.stats_cmd))

    app.add_handler(CommandHandler("adduser", h.adduser))
    app.add_handler(CommandHandler("removeuser", h.removeuser))
    app.add_handler(CommandHandler("listusers", h.listusers))

    media_filter = (
        filters.Document.ALL | filters.VIDEO | filters.AUDIO | filters.VOICE | filters.PHOTO
    ) & filters.ChatType.PRIVATE
    app.add_handler(MessageHandler(media_filter, h.save_incoming))

    # Persistent menu buttons + pending-search follow-up text, always last so
    # it never shadows a command handler above it.
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, h.on_menu_text)
    )

    app.add_handler(CallbackQueryHandler(h.on_callback))

    logging.info("Starting File Vault bot (polling)...")
    app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
