import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=True)

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS = [int(i.strip()) for i in os.getenv("ADMIN_IDS", "").split(",") if i.strip().isdigit()]
CAPSOLVER_API_KEY = os.getenv("CAPSOLVER_API_KEY", "").strip()

DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
MEDIA_DIR = BASE_DIR / "media"
MEDIA_DIR.mkdir(exist_ok=True)

_database_path = os.getenv("DATABASE_PATH", "data/bot.db").strip()
DB_PATH = Path(_database_path)
if not DB_PATH.is_absolute():
    DB_PATH = BASE_DIR / DB_PATH
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def mask_proxy(proxy: str) -> str:
    """Hide proxy credentials before displaying them to a Telegram user."""
    if not proxy:
        return "Без прокси"
    value = proxy.strip()
    if "@" in value:
        prefix, host = value.rsplit("@", 1)
        if "://" in prefix:
            scheme, auth = prefix.split("://", 1)
            user = auth.split(":", 1)[0]
            return f"{scheme}://{user}:***@{host}"
        return f"***@{host}"
    parts = value.split(":")
    if len(parts) == 4:
        return f"{parts[0]}:{parts[1]}:{parts[2][:3]}***:***"
    return value
