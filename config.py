import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DATABASE_URL = os.getenv("DATABASE_URL", "")
BASE_URL = "https://hist-ege.sdamgia.ru"
PARSE_DELAY = 0.5
