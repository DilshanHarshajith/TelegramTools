import os
import dotenv
dotenv.load_dotenv()

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
SESSION_NAME = "session"

DATA_DIR = "data"
GROUP_FILE = os.path.join(DATA_DIR, "groups.txt")
OUTPUT_DIR = os.path.join(DATA_DIR, "output")

DEFAULT_KEYWORD = ""
DEFAULT_LIMIT = 1000
