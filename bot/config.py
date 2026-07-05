import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHANNEL_ID = int(os.environ["CHANNEL_ID"])
OWNER_ID = int(os.environ["OWNER_ID"])
DB_PATH = os.environ.get("DB_PATH", "vault.db")
PAGE_SIZE = 10

# Optional: point at a self-hosted Bot API server (e.g. http://telegram-bot-api:8081)
# to raise the 50MB upload / 20MB download caps up to 2000MB. Leave unset to use
# the standard cloud API at api.telegram.org.
LOCAL_API_URL = os.environ.get("LOCAL_API_URL", "").rstrip("/")
