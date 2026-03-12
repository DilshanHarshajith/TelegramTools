"""
Universal Task Module Template
------------------------------
Instructions:
1. Copy this file and rename it for a new task module.
2. Implement your logic in process_item().
3. The module automatically handles:
   - Async Telegram client connection
   - Groups from CLI (file or direct links)
   - Per-group output folders
   - Optional --limit
   - Live progress tracking
"""

import os
import sys

# Add project root to sys.path if running as standalone script
if __name__ == "__main__":
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
from telethon import TelegramClient
from telethon.tl.types import User  # or other types your module needs
try:
    import config as _cfg
except ImportError:
    class _cfg:
        API_ID = os.getenv("API_ID")
        API_HASH = os.getenv("API_HASH")
        SESSION_NAME = "session"
        VERBOSE = True; INFO = True; SUCCESS = True; PROGRESS = True
        WARNING = False; ERROR = False
        GROUP_FILE = "data/groups.txt"

API_ID = _cfg.API_ID
API_HASH = _cfg.API_HASH
SESSION_NAME = _cfg.SESSION_NAME

def info(message): print(f"[*] {message}") if _cfg.VERBOSE or _cfg.INFO else None
def error(message): print(f"[!] {message}") if _cfg.VERBOSE or _cfg.ERROR else None
def warning(message): print(f"[!] {message}") if _cfg.VERBOSE or _cfg.WARNING else None
def success(message): print(f"[✓] {message}") if _cfg.VERBOSE or _cfg.SUCCESS else None
def progress(message): print(f"[+] {message}") if _cfg.VERBOSE or _cfg.PROGRESS else None

def get_client():
    return TelegramClient(SESSION_NAME, API_ID, API_HASH)

async def connect_client():
    client = get_client()
    try:
        await client.start()
        info("Connected to Telegram API")
        return client
    except Exception as e:
        error(f"Failed to connect to Telegram API: {e}")
        raise

def read_groups_from_file(file_path=None):
    path = file_path or _cfg.GROUP_FILE
    if not os.path.isfile(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

OUTPUT_DIR = os.getcwd()

# ------------------------
# CLI Arguments
# ------------------------
def get_args(parser):
    """
    Add module-specific CLI arguments here
    Example:
        parser.add_argument("--keyword", type=str, help="Search keyword")
    """
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Maximum number of messages/items to scan per group (0 = all)"
    )
    parser.add_argument(
        "--example",
        type=str,
        default="default",
        help="Example argument"
    )


# ------------------------
# Main entry point
# ------------------------
async def run(args):
    client = await connect_client()
    groups = args.groups or read_groups_from_file()
    module_output = os.path.join(OUTPUT_DIR, "module_template")  # adjust name

    for group in groups:
        await process_group(client, group, args, module_output)

    await client.disconnect()


# ------------------------
# Process each group
# ------------------------
async def process_group(client, group, args, module_output):
    """
    Handles per-group output folder, scanning, and progress display.
    Calls process_item() for each message/item.
    """
    group_safe = group.replace("/", "_")
    output_dir = os.path.join(module_output, group_safe)
    os.makedirs(output_dir, exist_ok=True)

    existing_items = set()
    total_messages = args.limit or await client.get_messages_count(group)
    scanned = 0
    new_items = 0

    async for msg in client.iter_messages(group, limit=args.limit or None):
        scanned += 1
        added = await process_item(client, msg, output_dir, args, existing_items)
        if added:
            new_items += 1

        # Live progress display
        print(f"\rScanning messages: {scanned}/{total_messages} | New items: {new_items}", end="")

    print(f"\n[✓] Processed {new_items} new items from {group} to {output_dir}")


# ------------------------
# Module-specific logic
# ------------------------
async def process_item(client, msg, output_dir, args, existing_items):
    """
    Replace this with your module logic.
    Return True if a new item was created (for progress counter), False otherwise.
    Examples:
    - Saving messages to CSV/JSON
    - Downloading media
    - Filtering by keyword
    """
    # Example: no-op (override this in your module)
    return False


if __name__ == "__main__":
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(description="Universal Task Module (Template)")
    get_args(parser)
    args = parser.parse_args()

    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass