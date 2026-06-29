import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DB_PATH = "/data/ege_history.db"
BASE_URL = "https://hist-ege.sdamgia.ru"
PARSE_DELAY = 1.5  # seconds between requests
