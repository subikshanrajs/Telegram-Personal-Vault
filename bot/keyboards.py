import math

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

MENU_BROWSE = "📂 Browse"
MENU_SEARCH = "🔍 Search"
MENU_COLLECTIONS = "🎬 Collections"
MENU_STATS = "📊 Stats"
MENU_GET_ALL = "📥 Get Everything"


def main_menu_keyboard():
    """Persistent bottom keyboard so common actions don't need typed commands."""
    return ReplyKeyboardMarkup(
        [
            [MENU_BROWSE, MENU_SEARCH],
            [MENU_COLLECTIONS, MENU_STATS],
            [MENU_GET_ALL],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def results_keyboard(rows, page, pages, query):
    """Flat /list results — one row per file, unchanged from before."""
    buttons = [
        [InlineKeyboardButton(f"📄 #{r['id']} {r['file_name']}", callback_data=f"get:{r['id']}")]
        for r in rows
    ]
    kind = "s" if query else "l"
    q = query or "-"
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"page:{kind}:{q}:{page - 1}"))
    if pages > 1:
        nav.append(InlineKeyboardButton(f"{page + 1}/{pages}", callback_data="noop"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"page:{kind}:{q}:{page + 1}"))
    if nav:
        buttons.append(nav)
    return InlineKeyboardMarkup(buttons)


def grouped_results_keyboard(items, page, pages, query):
    """Search results where files sharing a collection are folded into one
    row with a "Get All" shortcut instead of listing every episode."""
    buttons = []
    for it in items:
        if it[0] == "file":
            r = it[1]
            buttons.append(
                [InlineKeyboardButton(f"📄 #{r['id']} {r['file_name']}", callback_data=f"get:{r['id']}")]
            )
        else:
            _, cid, name, members = it
            buttons.append(
                [
                    InlineKeyboardButton(f"🎬 {name} ({len(members)})", callback_data=f"collbrowse:{cid}:0"),
                    InlineKeyboardButton("⬇️ Get All", callback_data=f"collget:{cid}"),
                ]
            )
    q = query or "-"
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"gpage:{q}:{page - 1}"))
    if pages > 1:
        nav.append(InlineKeyboardButton(f"{page + 1}/{pages}", callback_data="noop"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"gpage:{q}:{page + 1}"))
    if nav:
        buttons.append(nav)
    return InlineKeyboardMarkup(buttons)


def collections_keyboard(rows, page, pages):
    buttons = [
        [InlineKeyboardButton(f"🎬 {r['name']} ({r['cnt']})", callback_data=f"collbrowse:{r['id']}:0")]
        for r in rows
    ]
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"collpage:{page - 1}"))
    if pages > 1:
        nav.append(InlineKeyboardButton(f"{page + 1}/{pages}", callback_data="noop"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"collpage:{page + 1}"))
    if nav:
        buttons.append(nav)
    return InlineKeyboardMarkup(buttons)


def collection_browse_keyboard(cid, members, page, page_size=10):
    start = page * page_size
    page_members = members[start:start + page_size]
    buttons = [
        [InlineKeyboardButton(f"📄 {m['file_name']}", callback_data=f"get:{m['id']}")]
        for m in page_members
    ]
    pages = max(1, math.ceil(len(members) / page_size))
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"collbrowse:{cid}:{page - 1}"))
    if pages > 1:
        nav.append(InlineKeyboardButton(f"{page + 1}/{pages}", callback_data="noop"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"collbrowse:{cid}:{page + 1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton("⬇️ Get All in this collection", callback_data=f"collget:{cid}")])
    return InlineKeyboardMarkup(buttons)


def confirm_get_all_keyboard(count):
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(f"✅ Yes, send all {count}", callback_data="sendall:confirm"),
                InlineKeyboardButton("✖️ Cancel", callback_data="sendall:cancel"),
            ]
        ]
    )
