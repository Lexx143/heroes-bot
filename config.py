import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# Telegram Config
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_GROUP_CHAT_ID = os.getenv("TELEGRAM_GROUP_CHAT_ID") # Saved dynamically if not in env

# Google Sheets Config
GOOGLE_SHEET_TITLE = os.getenv("GOOGLE_SHEET_TITLE", "Красавчики - Учет Рабочего Времени")
SHARE_USER_EMAIL = os.getenv("SHARE_USER_EMAIL", "itsgaetz@gmail.com")
GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "google_creds.json")

# CrocoTime Config
CROCO_URL = os.getenv("CROCO_URL", "")
CROCO_LOGIN = os.getenv("CROCO_LOGIN", "")
CROCO_PASSWORD = os.getenv("CROCO_PASSWORD", "")
TOKEN_STORE_FILE = os.getenv("TOKEN_STORE_FILE", os.path.join(os.path.dirname(__file__), "token_store.json"))

# State File (for keeping track of TG group chat ID if not in env)
STATE_FILE = os.path.join(os.path.dirname(__file__), "bot_state.json")

def load_state():
    import json
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_state(state):
    import json
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=4)
    except Exception as e:
        print(f"[Config] Failed to save state file: {e}")
