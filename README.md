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

## 3. Deploy for free, 24/7 — self-host on your own PC (no signup, no card)

If you don't have a credit card, this is genuinely the best option — nearly
every cloud "free tier" (Oracle, AWS, GCP, IBM, Fly.io, Railway) requires card
verification even when nothing gets charged. Render is a rare card-free
exception, but its free tier only runs a single sleeping web service and has
no free background worker, which can't fit this project's two-container setup
without giving up the 2GB local API server or paying for an always-on plan.

Self-hosting has no such catch: it's what you've already been running in WSL
this whole time. The only real cost is keeping the machine on.

1. **Stop the PC from sleeping.** Windows Settings → System → Power & Battery
   → Screen and sleep → set "When plugged in, put my device to sleep" to
   **Never**.
2. **Make sure `docker.service` starts automatically inside WSL.** You already
   enabled this earlier:
   ```bash
   sudo systemctl enable docker
   ```
   Combined with `restart: unless-stopped` in `docker-compose.yml`, your
   containers come back up automatically whenever the Docker daemon starts —
   no need to manually run `docker compose up` again after a restart.
3. **The remaining gap**: WSL itself only boots when something triggers it
   (opening a terminal, etc.) — Windows doesn't start it automatically on its
   own. Fix this with a Task Scheduler entry that boots WSL at login:
   - Open **Task Scheduler** → Create Task
   - General tab: name it, check "Run whether user is logged on or not"
   - Triggers tab: New → **At log on**
   - Actions tab: New → Program/script: `wsl.exe`, Arguments:
     `-d <YourDistroName> -e true` (find your exact distro name from
     PowerShell with `wsl -l -v` — it's likely `Ubuntu` or `Ubuntu-24.04`)
   - Save it (you'll need to enter your Windows password once)
4. Optionally enable Windows auto-login for your account so step 3 fires
   without you manually signing in after a reboot (Settings → Accounts →
   Sign-in options, or `netplwiz` for the classic dialog).

With those three things in place — no sleep, Docker auto-starting, WSL booting
at login — your bot survives Windows updates and reboots the same way it
would on a cloud VM, just running on hardware you already own.

## 4. Deploy for free, 24/7 — Oracle Cloud (requires card verification)

If you get access to a credit or debit card later — Oracle, like most cloud
providers, accepts debit cards for the required verification, so this doesn't
necessarily mean an actual credit line — Oracle's Always Free tier is a real
always-on VM worth revisiting:

Oracle's Always Free tier includes a real ARM VM that never sleeps and never
expires. This is the only mainstream "free" tier that's genuinely free forever
rather than a trial credit, which matters because this bot needs a
long-running process (long-polling Telegram for updates) plus the local API
server running alongside it.

> **Note (as of June 2026):** Oracle reduced the Always Free Ampere A1
> allowance to **2 OCPUs / 12GB RAM total** across your account (previously
> 4/24). This bot is lightweight enough that it doesn't matter — 1 OCPU / 6GB
> is comfortable — but don't provision more than the new limit or Oracle will
> require you to shrink it later. Check
> [the current limits](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier.htm)
> before creating your instance, since these policies can shift again.

1. Sign up at [cloud.oracle.com](https://www.oracle.com/cloud/free/) (needs
   card verification, but the Always Free resources aren't billed).
2. Create an instance: **Compute → Create Instance** → choose the
   **Ampere (ARM) A1** shape, Ubuntu 22.04/24.04 image, **1–2 OCPU / 6–12GB**
   (the `aiogram/telegram-bot-api` image is multi-arch and runs natively on
   ARM). Going above 2 OCPU/12GB total across all your A1 instances risks
   Oracle shutting it down until you resize it back down.
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
8. **Guard against idle reclamation.** Oracle can reclaim a free-tier VM it
   judges idle (very low CPU, network, and memory usage sustained over a
   7-day window). A bot that mostly sits waiting for Telegram updates can
   look idle by that measure even while working correctly. A simple, cheap
   safeguard is a cron job that does a small amount of real work periodically:
   ```bash
   ( crontab -l 2>/dev/null; echo "*/10 * * * * dd if=/dev/urandom of=/dev/null bs=1M count=50" ) | crontab -
   ```
   This keeps CPU/memory activity above the reclamation threshold without
   costing anything or affecting the bot.

To update later: re-`scp` or `git pull`, then `docker compose up -d --build`.

### Prefer no Docker on the VM?

A plain-Python/systemd path (`deploy/telegram-vault.service`) is included
too, but it only gives you the 50MB/20MB cloud-API limits since it doesn't
run the local Bot API server — use it if you decide 2GB isn't worth the
extra moving part after all.

## 5. Alternative: any Docker host (Fly.io, Railway, etc.)

The same `docker-compose.yml` works anywhere Docker Compose runs. Worth
knowing before you pick one: Fly.io and Railway both now require credit card
verification even for their free/trial allowances, and Render's card-free free
tier only supports a single sleeping web service, not this project's
two-container setup, without paying for an always-on plan. If you have a card
available, Oracle (section 4) remains the best genuinely-free, always-on fit.

## Commands

| Command | Description |
|---|---|
| `/start` | Show help + persistent menu keyboard |
| *(send any file)* | Archive it; auto-grouped into a series if it looks like one |
| `/list [page]` | Browse everything, paginated |
| `/uncollected [page]` | Files not currently in any series |
| `/search <name>` | Search by filename or series name — episodes group into one result with a "Get All" button |
| `/collections [page]` | Browse all auto-detected series, with their ids |
| `/collection <id> <name>` | Fix one file's grouping (`/collection 5 -` to ungroup) |
| `/bulkcollection <ids> <name>` | Group a whole range at once — `/bulkcollection 120-150 Show Name`, or `5,7,9-12` for a mixed list |
| `/mergecollections <id> <id2>…` | Merge collections that got wrongly split — find ids from `/collections` |
| `/renamecollection <id> <name>` | Rename an entire series in one go |
| `/regroup` | Re-run the grouping algorithm on everything you haven't fixed by hand — safe to run any time, never touches manual fixes |
| `/duplicates` | Find files uploaded more than once (same underlying Telegram file) |
| `/rename <id> <new name>` | Rename a single entry |
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

When you upload files with names like `Show.S01E01.mkv`, `Breaking.Bad.1x05.mp4`,
or `Movie Name 2 (2012).mp4`, the bot strips episode/part/quality/language/release
tags and groups files that reduce to the same base name. `/search` then returns
one row per series with a `⬇️ Get All` button instead of ten separate results.

This is a heuristic, and it improves over time — if it split one show into two
collections (e.g. because of a tag it didn't know to strip yet), fix it in one
of two ways:

- **Retroactively re-run the algorithm on everything**: `/regroup`. This never
  touches files you've already fixed by hand, so it's always safe to run again
  after an update.
- **Merge specific collections directly**: find their ids with `/collections`,
  then `/mergecollections <keep_this_id> <merge_this_id>`.

To fix or organize files in bulk instead of one at a time, use
`/bulkcollection <ids> <name>` with a range (`120-150`), a list (`5,7,9`), or
both mixed together (`1,5-10,15`).

### Reliability with large batch uploads

Telegram recommends against bots sending more than ~20 messages/minute to the
same group or channel — every archived file triggers one such call to your
private channel, so uploading a big batch quickly can hit that ceiling. The bot
now uses `python-telegram-bot`'s built-in rate limiter, which automatically
paces outgoing calls and retries on Telegram's own backoff signal instead of
silently dropping files. If a file still fails after retries (rare), you'll get
an explicit ⚠️ message naming it, instead of it just vanishing — resend just
that one file.

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
