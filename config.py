import os
import sys
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
REPLY_ITER_LIMIT = 500

# Validate required API credentials
if not API_ID or not API_HASH:
    print("[!] Error: API_ID and API_HASH must be set in environment variables or .env file")
    sys.exit(1)
