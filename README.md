# Telegram File Vault

A personal file-storage bot. Send it any file, photo, video, audio, or voice
note in a private DM — it copies the message into a private Telegram channel
you own (free, effectively unlimited storage) and indexes the filename in a
local SQLite database (with full-text search) so you can find and re-download
it later.

Only you (one Telegram user id) can use it.

## How it works

- **Storage**: your private channel. Telegram doesn't delete channel content,
  and there's no per-account storage cap for normal use.
- **Index**: SQLite (`vault.db`) mapping `file name -> channel message id`.
  Retrieval uses `copy_message`, which re-sends straight from Telegram's
  servers — no re-uploading, so it's fast even for big files.
- **Limits**: this project runs a self-hosted
  [local Bot API server](https://github.com/tdlib/telegram-bot-api)
  alongside the bot (via Docker), which raises the file size cap from the
  cloud API's 50MB upload / 20MB download to **2000MB (2GB)** per file.

## 1. One-time Telegram setup

1. **Create the bot**: message [@BotFather](https://t.me/BotFather) →
   `/newbot` → save the token it gives you.
2. **Create a private channel**: Telegram app → New Channel → make it
   Private. This is your storage.
3. **Add the bot as admin** of that channel (Channel → Administrators → Add
   Admin → search your bot). It needs "Post Messages" and "Delete Messages"
   permissions.
4. **Get the channel's numeric id**:
   - Post any message in the channel.
   - Forward that message to [@userinfobot](https://t.me/userinfobot) — it
     won't show a channel id directly, so instead:
   - Visit `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser
     right after posting in the channel. Look for `"chat":{"id":-100...}` —
     that negative number is your `CHANNEL_ID`.
5. **Get your own user id**: message [@userinfobot](https://t.me/userinfobot)
   directly — it replies with your numeric `OWNER_ID`.
6. **Get an `api_id`/`api_hash`** at [my.telegram.org](https://my.telegram.org)
   → API Development Tools → fill in any app name/platform. These identify
   *your account* to Telegram's infrastructure and are required to run the
   local Bot API server (they are not your bot token — keep both secret).

## 2. Local setup (test before deploying)

Requires [Docker](https://docs.docker.com/get-docker/) and Docker Compose
(bundled with Docker Desktop; on Linux, `docker compose` ships with recent
Docker Engine installs).

```bash
cd telegram-file-vault
cp .env.example .env
# edit .env: fill in BOT_TOKEN, CHANNEL_ID, OWNER_ID, TELEGRAM_API_ID, TELEGRAM_API_HASH
docker compose up -d --build
docker compose logs -f vault-bot   # confirm it connects and starts polling
```

Message your bot on Telegram, send it a file (try something over 50MB to
confirm the local server path is working), then try `/list` and
`/search <name>`.

> **First time only**: if you'd previously run this bot against the cloud
> API, log it out first so the local server can take over polling:
> `curl https://api.telegram.org/bot<BOT_TOKEN>/logOut`

Prefer running without Docker / only need the 50MB cloud-API limit? Skip
`TELEGRAM_API_ID`/`TELEGRAM_API_HASH` and `LOCAL_API_URL` entirely, then:
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

## 3. Deploy for free, 24/7 — Oracle Cloud (recommended)

Oracle's Always Free tier includes a real ARM VM (up to 4 OCPU / 24GB RAM)
that never sleeps and never expires. This is the only mainstream "free"
tier that's genuinely free forever rather than a trial credit, which matters
because this bot needs a long-running process (long-polling Telegram for
updates) plus the local API server running alongside it.

1. Sign up at [cloud.oracle.com](https://www.oracle.com/cloud/free/) (needs
   card verification, but the Always Free resources aren't billed).
2. Create an instance: **Compute → Create Instance** → choose the
   **Ampere (ARM) A1** shape, Ubuntu 22.04/24.04 image, keep it within the
   Always Free allowance (e.g. 2 OCPU / 12GB is plenty for this bot — the
   `aiogram/telegram-bot-api` image is multi-arch and runs natively on ARM).
3. Download the SSH key it gives you, then connect:
   ```bash
   ssh -i your-key.pem ubuntu@<your-instance-public-ip>
   ```
4. Install Docker:
   ```bash
   curl -fsSL https://get.docker.com | sudo sh
   sudo usermod -aG docker $USER
   # log out and back in for the group change to take effect
   ```
5. Get the code onto the VM (no repo? use `scp` instead of `git clone`):
   ```bash
   scp -i your-key.pem -r telegram-file-vault ubuntu@<ip>:~/
   ssh -i your-key.pem ubuntu@<ip>
   cd telegram-file-vault
   cp .env.example .env
   nano .env   # fill in your real values
   ```
6. Bring it up — Compose's `restart: unless-stopped` policy handles crash
   recovery and reboots automatically, so no separate systemd unit is needed:
   ```bash
   docker compose up -d --build
   docker compose ps              # confirm both containers are healthy
   docker compose logs -f vault-bot
   ```
7. Oracle's default security list blocks all inbound traffic, which is fine
   here — both containers only make *outbound* calls to Telegram, and the
   local API server is only reachable from the bot container itself
   (`expose`, not `ports`, in `docker-compose.yml`).

To update later: re-`scp` or `git pull`, then `docker compose up -d --build`.

### Prefer no Docker on the VM?

A plain-Python/systemd path (`deploy/telegram-vault.service`) is included
too, but it only gives you the 50MB/20MB cloud-API limits since it doesn't
run the local Bot API server — use it if you decide 2GB isn't worth the
extra moving part after all.

## 4. Alternative: any Docker host (Fly.io, Railway, etc.)

The same `docker-compose.yml` works anywhere Docker Compose runs. Just be
aware free tiers on platforms like Render spin containers down after
inactivity, which breaks long-polling — only use a platform that gives you
an always-on free container (Fly.io's free allowance currently does;
Railway's free tier is a limited trial credit, not indefinite).

## Commands

| Command | Description |
|---|---|
| `/start` | Show help + persistent menu keyboard |
| *(send any file)* | Archive it; auto-grouped into a series if it looks like one |
| `/list [page]` | Browse everything, paginated |
| `/search <name>` | Search by filename or series name — episodes group into one result with a "Get All" button |
| `/collections [page]` | Browse all auto-detected series |
| `/collection <id> <name>` | Fix a file's grouping manually (`/collection 5 -` to ungroup) |
| `/rename <id> <new name>` | Rename an entry |
| `/delete <id>` | Remove from channel + index |
| `/stats` | Count and total size by file type |
| `/whoami` | Show your Telegram ID (send this to the owner to request access) |
| `/adduser <id>` *(owner only)* | Grant another Telegram account full access |
| `/removeuser <id>` *(owner only)* | Revoke access |
| `/listusers` *(owner only)* | List everyone with access |

The bottom keyboard (📂 Browse / 🔍 Search / 🎬 Collections / 📊 Stats / 📥 Get Everything)
covers the everyday actions without typing `/` — tap 🔍 Search, then just send
the name you're looking for as a plain message.

### Series auto-grouping

When you upload files with names like `Show.S01E01.mkv`, `Show.S01E02.mkv`, or
`Movie Name 1 (2012).mp4`, `Movie Name 2 (2012).mp4`, the bot strips episode/part/
year markers and groups files that reduce to the same base name. `/search` then
returns one row per series with a `⬇️ Get All` button instead of ten separate
results. This is a heuristic, not perfect — use `/collection <id> <name>` to fix
a wrong grouping, or `/collection <id> -` to remove a file from a group entirely.

### Multiple accounts

`OWNER_ID` in `.env` is the permanent owner and can never be removed. To let a
friend or another of your own accounts use the same vault:

1. Have them message the bot and send `/whoami` to get their numeric ID
2. You run `/adduser <that id>`

They then get full access — uploading, searching, browsing, deleting — same as
you, just without the ability to add/remove other users.

### Getting everything back out

Tap **📥 Get Everything** (or the "✅ Yes, send all N" confirmation it shows) to
have the bot re-send every stored file to you in one go, throttled to stay clear
of Telegram's flood limits. Useful if you're migrating away or just want a full
local copy. The same "Get All" mechanism works per-series from `/collections`
or from a grouped `/search` result.


## Backing up the index

`vault.db` is the only thing that isn't recoverable from Telegram itself if
lost (the files stay safe in your channel either way). Worth an occasional
copy:

```bash
scp -i your-key.pem ubuntu@<ip>:~/telegram-file-vault/vault.db ./vault-backup.db
```
