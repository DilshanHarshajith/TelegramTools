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

# Output settings
VERBOSE = True
INFO = True
SUCCESS = True
WARNING = False
ERROR = False
PROGRESS = True

# Ignore modules
DISCOVER_IGNORE = ['!']
WEB_IGNORE = ['#']

#File path patterns regex
# Matches "saved to [path]", "Saved to [path]", "exported to [path]" or even "Processing group: [name]" (which we can guess the path for)
FILE_PATH_PATTERNS = [
            r'[Ss]aved to\s+([\w\-/\\:. ]+)',
            r'[Ee]xported to\s+([\w\-/\\:. ]+)',
            r'[Rr]esults for this group are in\s+([\w\-/\\:. ]+)',
            r'[Oo]utput(?:\s+path)?[:\s]+([\w\-/\\:. ]+)',
            r'[Pp]rocessing group[:\s]+([\w\-/\\:. ]+)',
            r'[Cc]ollecting (?:infrastructure|data) for[:\s]+([\w\-/\\:. ]+)'
        ]

# Validate required API credentials
if not API_ID or not API_HASH:
    print("[!] Error: API_ID and API_HASH must be set in environment variables or .env file")
    sys.exit(1)
