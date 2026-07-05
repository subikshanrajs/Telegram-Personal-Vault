import asyncio
import logging
import math

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from . import database as db
from .auth import allowed_only, owner_only
from .config import CHANNEL_ID, PAGE_SIZE
from .keyboards import (
    MENU_BROWSE,
    MENU_COLLECTIONS,
    MENU_GET_ALL,
    MENU_SEARCH,
    MENU_STATS,
    collection_browse_keyboard,
    collections_keyboard,
    confirm_get_all_keyboard,
    grouped_results_keyboard,
    main_menu_keyboard,
    results_keyboard,
)

logger = logging.getLogger(__name__)

SEND_DELAY = 0.35  # seconds between messages during bulk sends, to stay clear of flood limits


def human_size(n):
    if not n:
        return "unknown size"
    n = float(n)
    for unit in ["B", "KB", "MB", "GB"]:
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


@allowed_only
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📦 *File Vault Bot*\n\n"
        "Send me any file, photo, video, audio, or voice note and I'll archive it "
        "to your private storage channel and index it by name. Files that look "
        "like episodes of the same series are grouped automatically.\n\n"
        "Use the buttons below, or these commands:\n"
        "/search <name> — search by filename or series\n"
        "/collections — browse auto-grouped series\n"
        "/collection <id> <name> — fix a file's grouping manually\n"
        "/rename <id> <new name> — rename an entry\n"
        "/delete <id> — remove an entry\n"
        "/stats — storage summary\n"
        "/whoami — show your Telegram ID (to request access)",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_keyboard(),
    )


async def whoami(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(f"Your Telegram ID is `{user.id}`.", parse_mode=ParseMode.MARKDOWN)


@allowed_only
async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Menu:", reply_markup=main_menu_keyboard())


@allowed_only
async def save_incoming(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    file_obj = None
    file_type = None
    default_name = None

    if msg.document:
        file_obj, file_type = msg.document, "document"
        default_name = msg.document.file_name or f"document_{msg.message_id}"
    elif msg.video:
        file_obj, file_type = msg.video, "video"
        default_name = msg.video.file_name or f"video_{msg.message_id}.mp4"
    elif msg.audio:
        file_obj, file_type = msg.audio, "audio"
        title = msg.audio.title or "audio"
        default_name = msg.audio.file_name or f"{title}_{msg.message_id}.mp3"
    elif msg.voice:
        file_obj, file_type = msg.voice, "voice"
        default_name = f"voice_{msg.message_id}.ogg"
    elif msg.photo:
        file_obj, file_type = msg.photo[-1], "photo"
        default_name = f"photo_{msg.message_id}.jpg"
    else:
        return

    copied = await context.bot.copy_message(
        chat_id=CHANNEL_ID,
        from_chat_id=msg.chat_id,
        message_id=msg.message_id,
    )

    file_size = getattr(file_obj, "file_size", None)

    record_id, collection_name = db.add_file(
        file_name=default_name,
        file_type=file_type,
        file_size=file_size,
        telegram_file_id=getattr(file_obj, "file_id", None),
        telegram_unique_id=getattr(file_obj, "file_unique_id", None),
        channel_message_id=copied.message_id,
        caption=msg.caption,
        uploaded_by=update.effective_user.id,
    )

    series_line = f"\nSeries: *{collection_name}*" if collection_name else ""
    await msg.reply_text(
        f"✅ Archived as *#{record_id}* — `{default_name}`\n"
        f"Type: {file_type} · Size: {human_size(file_size)}{series_line}\n\n"
        f"Rename: `/rename {record_id} new_name.ext`"
        + (f"\nFix grouping: `/collection {record_id} Correct Series Name`" if collection_name else ""),
        parse_mode=ParseMode.MARKDOWN,
    )


# --- Browsing / search ---------------------------------------------------------


@allowed_only
async def list_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    page = 0
    if context.args and context.args[0].isdigit():
        page = max(0, int(context.args[0]) - 1)
    rows, total = db.list_files(page, PAGE_SIZE)
    if not rows:
        await update.effective_message.reply_text("No files found.")
        return
    pages = max(1, math.ceil(total / PAGE_SIZE))
    header = f"Results {page * PAGE_SIZE + 1}-{page * PAGE_SIZE + len(rows)} of {total}:"
    await update.effective_message.reply_text(header, reply_markup=results_keyboard(rows, page, pages, None))


@allowed_only
async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /search <name or keyword>")
        return
    query = " ".join(context.args)
    await _send_grouped_search(update, context, query, 0)


async def _send_grouped_search(update, context, query, page):
    items, total = db.search_grouped(query, page, PAGE_SIZE)
    if not items:
        await update.effective_message.reply_text("No files found.")
        return
    pages = max(1, math.ceil(total / PAGE_SIZE))
    header = f"Results {page * PAGE_SIZE + 1}-{page * PAGE_SIZE + len(items)} of {total}:"
    kb = grouped_results_keyboard(items, page, pages, query)
    await update.effective_message.reply_text(header, reply_markup=kb)


@allowed_only
async def collections_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    page = 0
    if context.args and context.args[0].isdigit():
        page = max(0, int(context.args[0]) - 1)
    rows, total = db.list_collections(page, PAGE_SIZE)
    if not rows:
        await update.effective_message.reply_text(
            "No series detected yet — upload 2+ files that share a common base name "
            "(like TV episodes) and I'll group them automatically."
        )
        return
    pages = max(1, math.ceil(total / PAGE_SIZE))
    await update.effective_message.reply_text(
        f"{total} series/collections:", reply_markup=collections_keyboard(rows, page, pages)
    )


@allowed_only
async def set_collection_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text(
            "Usage: /collection <file_id> <series name>\n"
            "Use `/collection <file_id> -` to remove it from any collection."
        )
        return
    file_id = int(context.args[0])
    rest = context.args[1:]
    if not db.get_file(file_id):
        await update.message.reply_text("No such entry.")
        return
    name = None if (len(rest) == 1 and rest[0] == "-") else (" ".join(rest) if rest else None)
    db.set_file_collection(file_id, name)
    if name:
        await update.message.reply_text(f"#{file_id} added to *{name}*", parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(f"#{file_id} removed from its collection.")


# --- Bulk "get everything" ------------------------------------------------------


@allowed_only
async def get_everything_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    count = db.total_file_count()
    if count == 0:
        await update.effective_message.reply_text("Nothing stored yet.")
        return
    await update.effective_message.reply_text(
        f"This will send all *{count}* stored files to you, one by one. Continue?",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=confirm_get_all_keyboard(count),
    )


async def _bulk_send(context, chat_id, files, label):
    sent = 0
    for f in files:
        try:
            await context.bot.copy_message(
                chat_id=chat_id, from_chat_id=CHANNEL_ID, message_id=f["channel_message_id"]
            )
            sent += 1
        except Exception:
            logger.exception("Failed to resend file #%s during bulk send", f["id"])
        await asyncio.sleep(SEND_DELAY)
        if sent and sent % 20 == 0:
            await context.bot.send_message(chat_id, f"…{sent}/{len(files)} sent so far")
    await context.bot.send_message(chat_id, f"✅ Done — sent {sent}/{len(files)} files from {label}.")


# --- Rename / delete / stats -----------------------------------------------------


@allowed_only
async def rename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2 or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /rename <id> <new name>")
        return
    file_id = int(context.args[0])
    new_name = " ".join(context.args[1:])
    if not db.get_file(file_id):
        await update.message.reply_text("No such entry.")
        return
    db.rename_file(file_id, new_name)
    await update.message.reply_text(f"Renamed #{file_id} → `{new_name}`", parse_mode=ParseMode.MARKDOWN)


@allowed_only
async def delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /delete <id>")
        return
    file_id = int(context.args[0])
    record = db.get_file(file_id)
    if not record:
        await update.message.reply_text("No such entry.")
        return
    try:
        await context.bot.delete_message(chat_id=CHANNEL_ID, message_id=record["channel_message_id"])
    except Exception:
        pass
    db.delete_file(file_id)
    await update.message.reply_text(f"Deleted #{file_id} ({record['file_name']}).")


@allowed_only
async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    count, total_size, by_type = db.stats()
    lines = [f"📊 *{count}* files · *{human_size(total_size)}* total"]
    for ftype, n in by_type:
        lines.append(f"  {ftype}: {n}")
    await update.effective_message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


# --- User management (owner only) -----------------------------------------------


@owner_only
async def adduser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text(
            "Usage: /adduser <telegram_id>\n"
            "Ask the person to send /whoami to the bot to get their ID."
        )
        return
    new_id = int(context.args[0])
    db.add_allowed_user(new_id, added_by=update.effective_user.id)
    await update.message.reply_text(f"✅ Added `{new_id}` — they now have full access.", parse_mode=ParseMode.MARKDOWN)
    try:
        await context.bot.send_message(
            chat_id=new_id,
            text="✅ You've been granted access to the File Vault bot. Send /start to begin.",
        )
    except Exception:
        pass  # they may not have messaged the bot yet — fine, they'll see it on /start


@owner_only
async def removeuser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /removeuser <telegram_id>")
        return
    target_id = int(context.args[0])
    db.remove_allowed_user(target_id)
    await update.message.reply_text(f"Removed `{target_id}` (unless they're the owner).", parse_mode=ParseMode.MARKDOWN)


@owner_only
async def listusers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = db.list_allowed_users()
    lines = ["👥 *Allowed users*"]
    for r in rows:
        role = "owner" if r["is_owner"] else "member"
        lines.append(f"`{r['user_id']}` — {role}")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


# --- Persistent menu button text handler -----------------------------------------


@allowed_only
async def on_menu_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == MENU_BROWSE:
        await list_files(update, context)
    elif text == MENU_SEARCH:
        context.user_data["awaiting_search"] = True
        await update.message.reply_text("What are you looking for? Send a name or keyword.")
    elif text == MENU_COLLECTIONS:
        await collections_cmd(update, context)
    elif text == MENU_STATS:
        await stats_cmd(update, context)
    elif text == MENU_GET_ALL:
        await get_everything_start(update, context)
    elif context.user_data.get("awaiting_search"):
        context.user_data["awaiting_search"] = False
        await _send_grouped_search(update, context, text, 0)
    else:
        await update.message.reply_text("Use the menu below, or /start for the command list.")


# --- Callback query dispatch -------------------------------------------------


@allowed_only
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = update.effective_user.id

    if data == "noop":
        return

    if data.startswith("get:"):
        file_id = int(data.split(":", 1)[1])
        record = db.get_file(file_id)
        if not record:
            await query.message.reply_text("That entry no longer exists.")
            return
        await context.bot.copy_message(
            chat_id=chat_id, from_chat_id=CHANNEL_ID, message_id=record["channel_message_id"]
        )
        return

    if data.startswith("page:"):
        _, kind, q, p = data.split(":", 3)
        page = int(p)
        q = None if q == "-" else q
        rows, total = db.list_files(page, PAGE_SIZE)
        pages = max(1, math.ceil(total / PAGE_SIZE))
        await query.edit_message_reply_markup(reply_markup=results_keyboard(rows, page, pages, None))
        return

    if data.startswith("gpage:"):
        _, q, p = data.split(":", 2)
        page = int(p)
        items, total = db.search_grouped(q, page, PAGE_SIZE)
        pages = max(1, math.ceil(total / PAGE_SIZE))
        await query.edit_message_reply_markup(reply_markup=grouped_results_keyboard(items, page, pages, q))
        return

    if data.startswith("collpage:"):
        page = int(data.split(":", 1)[1])
        rows, total = db.list_collections(page, PAGE_SIZE)
        pages = max(1, math.ceil(total / PAGE_SIZE))
        await query.edit_message_reply_markup(reply_markup=collections_keyboard(rows, page, pages))
        return

    if data.startswith("collbrowse:"):
        _, cid, p = data.split(":", 2)
        cid, page = int(cid), int(p)
        name, members = db.collection_files(cid)
        if not members:
            await query.message.reply_text("That collection is empty.")
            return
        text = f"🎬 *{name}* — {len(members)} files"
        kb = collection_browse_keyboard(cid, members, page)
        try:
            await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
        except Exception:
            await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
        return

    if data.startswith("collget:"):
        cid = int(data.split(":", 1)[1])
        name, members = db.collection_files(cid)
        if not members:
            await query.message.reply_text("That collection is empty.")
            return
        await query.message.reply_text(f"Sending all {len(members)} files in *{name}*…", parse_mode=ParseMode.MARKDOWN)
        await _bulk_send(context, chat_id, members, name)
        return

    if data == "sendall:cancel":
        await query.edit_message_text("Cancelled.")
        return

    if data == "sendall:confirm":
        files = db.all_files()
        await query.edit_message_text(f"Sending all {len(files)} files — this may take a while…")
        await _bulk_send(context, chat_id, files, "your vault")
        return
