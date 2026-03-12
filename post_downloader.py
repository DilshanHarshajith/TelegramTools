"""
Profile Posts Downloader
------------------------
Downloads all posts (stories/profile posts) from a Telegram user's profile page.
Supports paginated fetching of active and pinned posts, resume on restart,
and deduplication by story ID.
"""

import os
import sys
import asyncio

from telethon.tl.functions.stories import (
    GetPeerStoriesRequest,
    GetPinnedStoriesRequest,
    GetStoriesArchiveRequest,
)

from telethon import TelegramClient
# ---------------------------------------------------------------------------
# Path setup — makes config.py importable from anywhere
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

try:
    import config as _cfg
except ImportError:
    import getpass
    from pathlib import Path

    def _load_dotenv(path):
        vals = {}
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, val = line.partition("=")
                    vals[key.strip()] = val.strip().strip('"').strip("'")
        except OSError:
            pass
        return vals

    class _cfg:
        _api_id = _api_hash = None
        _session = "session"
        VERBOSE = True; INFO = True; SUCCESS = True; PROGRESS = True
        WARNING = False; ERROR = False
        GROUP_FILE = "groups.txt"
        DEFAULT_LIMIT = 1000
        REPLY_ITER_LIMIT = 500

        _here = Path(__file__).resolve().parent
        for _p in dict.fromkeys([_here / ".env", Path.home() / ".env", Path.cwd() / ".env"]):
            if _p.is_file():
                _d = _load_dotenv(_p)
                _api_id   = _d.get("API_ID")   or _api_id
                _api_hash = _d.get("API_HASH")  or _api_hash
                _session  = _d.get("SESSION_NAME", _session)
                if _api_id and _api_hash:
                    print(f"[*] Credentials loaded from {_p}")
                    break

        if not (_api_id and _api_hash):
            _api_id   = os.getenv("API_ID")   or _api_id
            _api_hash = os.getenv("API_HASH") or _api_hash

        if not (_api_id and _api_hash):
            print("\n[!] Telegram API credentials not found.")
            print("    Get yours at https://my.telegram.org/apps\n")
            while not _api_id:
                _raw = input("    API_ID  (numeric): ").strip()
                if _raw.isdigit():
                    _api_id = _raw
                else:
                    print("    API_ID must be a number — please try again.")
            while not _api_hash:
                _raw = getpass.getpass("    API_HASH (hidden): ").strip()
                if _raw:
                    _api_hash = _raw
                else:
                    print("    API_HASH cannot be empty — please try again.")
            if input("\n    Save to .env in current directory? [y/N] ").strip().lower() == "y":
                _env_path = Path.cwd() / ".env"
                with open(_env_path, "a", encoding="utf-8") as _f:
                    _f.write(f"\nAPI_ID={_api_id}\nAPI_HASH={_api_hash}\n")
                print(f"    Saved to {_env_path}\n")

        API_ID       = int(_api_id)
        API_HASH     = str(_api_hash)
        SESSION_NAME = _session

API_ID       = _cfg.API_ID
API_HASH     = _cfg.API_HASH
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

OUTPUT_DIR = os.getcwd()


# ---------------------------------------------------------------------------
# CLI Arguments
# ---------------------------------------------------------------------------

def get_args(parser):
    parser.add_argument(
        "usernames",
        nargs="+",
        help="One or more Telegram usernames (e.g. @username) to download profile posts from.",
    )
    parser.add_argument(
        "-w", "--workers",
        type=int,
        default=4,
        help="Number of concurrent downloads per user (default: 4).",
    )
    parser.add_argument(
        "--out",
        type=str,
        default=None,
        help="Output directory (default: data/output/post_downloader).",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Ignore previously downloaded files and re-download everything.",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_downloaded_ids(folder: str) -> set:
    """
    Scan an existing download folder and return a set of already-downloaded
    story IDs (int). Files are named like '12345', '12345.mp4', '12345.jpg'.
    """
    ids = set()
    if not os.path.isdir(folder):
        return ids
    for fname in os.listdir(folder):
        stem = fname.split(".")[0]
        if stem.isdigit():
            ids.add(int(stem))
    return ids


async def fetch_all_pinned(client, peer) -> list:
    """Paginate through ALL pinned profile posts (100 per page)."""
    all_pinned = []
    offset_id = 0
    while True:
        result = await client(
            GetPinnedStoriesRequest(peer=peer, offset_id=offset_id, limit=100)
        )
        batch = result.stories
        if not batch:
            break
        all_pinned.extend(batch)
        progress(f"  Pinned: fetched {len(all_pinned)} so far...")
        offset_id = batch[-1].id
        if len(batch) < 100:
            break
    return all_pinned


async def fetch_all_archived(client, peer) -> list:
    """
    Paginate through archived profile posts.
    Only accessible for the authenticated account's own profile;
    silently returns [] for other users.
    """
    all_archived = []
    offset_id = 0
    while True:
        try:
            result = await client(
                GetStoriesArchiveRequest(peer=peer, offset_id=offset_id, limit=100)
            )
            batch = result.stories
            if not batch:
                break
            all_archived.extend(batch)
            progress(f"  Archived: fetched {len(all_archived)} so far...")
            offset_id = batch[-1].id
            if len(batch) < 100:
                break
        except Exception:
            # Archive is only visible to the account owner — skip silently
            break
    return all_archived


async def download_story(client, story, sem, folder, downloaded_ids):
    """Download a single story with semaphore-limited concurrency."""
    async with sem:
        try:
            if not (hasattr(story, "media") and story.media):
                return
            filename = os.path.join(folder, str(story.id))
            await client.download_media(story.media, file=filename)
            downloaded_ids.add(story.id)
            progress(f"Downloaded story {story.id}")
        except Exception as e:
            warning(f"Failed to download story {story.id}: {e}")


# ---------------------------------------------------------------------------
# Per-user logic
# ---------------------------------------------------------------------------

async def process_user(client, username: str, args, base_output: str):
    safe_name = username.replace("@", "")
    folder = os.path.join(base_output, safe_name)
    os.makedirs(folder, exist_ok=True)

    # Resume: load already-downloaded IDs
    downloaded_ids: set = set()
    if not args.no_resume:
        downloaded_ids = get_downloaded_ids(folder)
        if downloaded_ids:
            info(f"Resuming for {username} — {len(downloaded_ids)} file(s) already on disk.")

    info(f"Resolving {username}...")
    try:
        peer = await client.get_entity(username)
    except Exception as e:
        error(f"Could not resolve {username}: {e}")
        return

    all_stories = []

    # 1. Active (non-expired) posts
    try:
        result = await client(GetPeerStoriesRequest(peer=peer))
        active = result.stories.stories
        all_stories.extend(active)
        info(f"Active posts: {len(active)}")
    except Exception as e:
        warning(f"Could not fetch active posts for {username}: {e}")

    # 2. Pinned posts (paginated — no 100-item cap)
    info("Fetching pinned posts...")
    try:
        pinned = await fetch_all_pinned(client, peer)
        all_stories.extend(pinned)
        info(f"Pinned posts total: {len(pinned)}")
    except Exception as e:
        warning(f"Could not fetch pinned posts for {username}: {e}")

    # 3. Archived posts (own account only — harmlessly skipped otherwise)
    info("Fetching archived posts...")
    archived = await fetch_all_archived(client, peer)
    if archived:
        all_stories.extend(archived)
        info(f"Archived posts total: {len(archived)}")

    # Deduplicate by story ID
    seen: set = set()
    unique_stories = []
    for s in all_stories:
        if s.id not in seen:
            seen.add(s.id)
            unique_stories.append(s)

    # Filter out already-downloaded
    to_download = [s for s in unique_stories if s.id not in downloaded_ids]

    info(f"Total unique posts : {len(unique_stories)}")
    info(f"Already downloaded : {len(downloaded_ids)}")
    info(f"To download now    : {len(to_download)}")

    if not to_download:
        success(f"Nothing new to download for {username}.")
        return

    sem = asyncio.Semaphore(args.workers)
    tasks = [
        asyncio.create_task(download_story(client, story, sem, folder, downloaded_ids))
        for story in to_download
    ]

    completed = 0
    total = len(tasks)
    for coro in asyncio.as_completed(tasks):
        await coro
        completed += 1
        print(f"\r  Progress: {completed}/{total}", end="", flush=True)

    print()  # newline after progress
    success(f"Done — downloaded {len(downloaded_ids) - (len(unique_stories) - total)} new file(s) for {username} → {folder}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def run(args):
    client = await connect_client()
    base_output = args.out if args.out else os.path.join(OUTPUT_DIR, "post_downloader")
    os.makedirs(base_output, exist_ok=True)

    try:
        for username in args.usernames:
            await process_user(client, username, args, base_output)
    except KeyboardInterrupt:
        warning("Interrupted by user.")
    finally:
        try:
            await client.disconnect()
        except Exception as e:
            warning(f"Error disconnecting: {e}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Download profile stories and posts from a Telegram user's profile page.",
        epilog="Examples:\n  python post_downloader.py @username\n  python post_downloader.py @user1 @user2 --out ./stories\n  python post_downloader.py @username --no-resume -w 8",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    get_args(parser)
    parsed = parser.parse_args()

    try:
        asyncio.run(run(parsed))
    except KeyboardInterrupt:
        pass