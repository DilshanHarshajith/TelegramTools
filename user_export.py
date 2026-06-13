import os
import argparse
import sys
import re

import asyncio
import csv
from telethon.tl.types import User, PeerUser
from telethon import TelegramClient
from telethon.errors import FloodWaitError
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

def read_existing_user_ids(csv_path):
    existing_uids = set()
    if not os.path.isfile(csv_path):
        return existing_uids
    try:
        with open(csv_path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if "user_id" in row:
                    existing_uids.add(row["user_id"])
    except (csv.Error, KeyError, OSError) as e:
        warning(f"Could not read existing CSV file: {e}")
        warning("Starting with empty user list")
    return existing_uids

def write_user_to_csv(csv_path, user_id, username, first_name, last_name, file_exists=False):
    with open(csv_path, "a", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        if not file_exists:
            writer.writerow(["user_id", "username", "first_name", "last_name"])
        writer.writerow([str(user_id), username or "", first_name or "", last_name or ""])

async def download_user_photo(client, user, output_dir, user_id=None, verbose=False):
    if not isinstance(user, User):
        if verbose:
            error(f"Skipping non-User entity: {type(user).__name__}")
        return False, "not_user"
    if not user.photo:
        if verbose:
            progress(f"User {user.id} has no profile photo")
        return False, "no_photo"
    user_id = user_id or str(user.id)
    filename = os.path.join(output_dir, f"{user_id}.jpg")
    if os.path.isfile(filename):
        if verbose:
            progress(f"Skipping {user_id}: file already exists")
        return False, "skipped_exists"
    try:
        await client.download_profile_photo(user, file=filename)
        if verbose:
            username = getattr(user, 'username', None) or user_id
            success(f"Downloaded: {username}")
        return True, "success"
    except FloodWaitError as e:
        warning(f"Flood wait {e.seconds}s. Waiting...")
        await asyncio.sleep(e.seconds)
        try:
            await client.download_profile_photo(user, file=filename)
            if verbose:
                username = getattr(user, 'username', None) or user_id
                success(f"Downloaded: {username}")
            return True, "success"
        except Exception as retry_e:
            if verbose:
                error(f"Failed to download photo for {user_id} after retry: {retry_e}")
            return False, "failed"
    except Exception as e:
        if verbose:
            error(f"Failed to download photo for {user_id}: {e}")
        return False, "failed"

async def download_photos_batch(client, users, output_dir, verbose=False):
    successful = 0
    skipped = 0
    no_photo = 0
    failed = 0
    for user in users:
        success_flag, status = await download_user_photo(client, user, output_dir, verbose=verbose)
        if success_flag:
            successful += 1
        elif status == "skipped_exists":
            skipped += 1
        elif status == "no_photo":
            no_photo += 1
        else:
            failed += 1
    return successful, skipped, no_photo, failed

def format_download_stats(successful, skipped, no_photo, failed):
    parts = [f"{successful} downloaded"]
    if skipped > 0:
        parts.append(f"{skipped} skipped (already exist)")
    if no_photo > 0:
        parts.append(f"{no_photo} no photo")
    if failed > 0:
        parts.append(f"{failed} failed")
    return ", ".join(parts)

async def fetch_full_user(client, user_or_id):
    try:
        if isinstance(user_or_id, int):
            user = await client.get_entity(user_or_id)
        elif isinstance(user_or_id, PeerUser):
            user = await client.get_entity(user_or_id)
        else:
            user = await client.get_entity(user_or_id.id)
        if isinstance(user, User):
            return user
    except Exception:
        pass
    return None

OUTPUT_DIR = os.getcwd()
from tqdm.asyncio import tqdm_asyncio
from tqdm import tqdm

def get_args(parser):
    parser.add_argument(
        "groups",
        nargs="+",
        help="Telegram group links or a file containing groups"
    )
    parser.add_argument(
        "--no-photos",
        action="store_false",
        dest="download_photos",
        help="Disable downloading profile photos (default: photos are downloaded)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Maximum number of messages to scan per group (0 = all)"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show usernames next to progress bar(default: False)"
    )
    parser.add_argument(
        "--out",
        type=str,
        help="Output directory (default: data/output/user_export)"
    )

async def run(args):
    client = await connect_client()
    module_output = args.out if args.out else os.path.join(OUTPUT_DIR, "user_export")
    os.makedirs(module_output, exist_ok=True)

    try:
        # Mode: Scan messages from groups
        for group in args.groups:
            await scan_group_messages(client, group, args, module_output)

    except KeyboardInterrupt:
        error("\nUser interrupted, stopping...")
    finally:
        try:
            await client.disconnect()
        except Exception as e:
            warning(f"Error disconnecting client: {e}")





async def resolve_message_sender(client, msg, verbose=False):
    """
    Resolve the sender of a message to a User object, ensuring username is present if possible.
    """
    sender = msg.sender
    
    # helper for clean logging
    def log(text):
        if verbose:
            tqdm_asyncio.write(text)

    # 1. If sender is None but we have an ID, try to fetch
    if sender is None and msg.sender_id:
        try:
            sender = await client.get_entity(msg.sender_id)
        except Exception:
            log(f"[!] Could not fetch sender for message {msg.id}")
            return None

    if not sender:
        return None

    # 2. If it's a User, check if we need to fetch full details (e.g. for username)
    if isinstance(sender, User):
        if not getattr(sender, 'username', None):
            full_user = await fetch_full_user(client, sender)
            if full_user and getattr(full_user, 'username', None):
                return full_user
        return sender
        
    log(f"[!] Skipping non-User sender: {type(sender).__name__}")
    return None


async def scan_group_messages(client, group, args, module_output):
    """
    Scan messages in a group to find unique users.
    """
    s = str(group).strip()
    s = re.sub(r'^(https?://)?(t\.me|telegram\.me|telegram\.dog)/', '', s, flags=re.IGNORECASE)
    s = re.sub(r'^(joinchat/|\+)', '', s)
    s = re.sub(r'^@', '', s)
    group_safe = re.sub(r'[/\\:*?"<>|]', "_", s)
    output_dir = os.path.join(module_output, group_safe)
    os.makedirs(output_dir, exist_ok=True)
    
    csv_file_path = os.path.join(output_dir, "visible_users.csv")
    csv_exists = os.path.isfile(csv_file_path)
    existing_uids = read_existing_user_ids(csv_file_path)
    
    info(f"Processing group: {group}")

    new_users = []
    scanned = 0
    limit = args.limit or None

    try:
        async for msg in tqdm_asyncio(client.iter_messages(group, limit=limit), desc="Scanning messages"):
            scanned += 1
            
            sender = await resolve_message_sender(client, msg, verbose=args.verbose)
            if not sender:
                continue
            
            uid = str(sender.id)
            if uid in existing_uids:
                continue
            
            new_users.append(sender)
            existing_uids.add(uid)
            if args.verbose:
                tqdm_asyncio.write(f"{sender.first_name or ''} | {uid}")

    except KeyboardInterrupt:
        warning("\nCtrl+C detected, stopping scanning...")

    finally:
        # Save CSV
        if new_users:
            info(f"Saving {len(new_users)} new users to CSV...")
            curr_csv_exists = csv_exists
            for sender in new_users:
                username = getattr(sender, 'username', None) or ""
                write_user_to_csv(
                    csv_file_path,
                    str(sender.id),
                    username,
                    sender.first_name or "",
                    sender.last_name or "",
                    curr_csv_exists
                )
                curr_csv_exists = True
        
        success(f"Scanned {scanned} messages, found {len(new_users)} new users")

        if args.download_photos and new_users:
             await process_photo_downloads(client, new_users, output_dir, args)


async def process_photo_downloads(client, users, output_dir, args):
    """
    Download photos for a list of Users.
    """
    if not args.download_photos:
        warning("--no-photos set, skipping photo download")
        return

    if not users:
        warning("No valid users to download photos for.")
        return

    info(f"Starting download for {len(users)} users...")
    
    successful, skipped, no_photo, failed = await download_photos_batch(
        client, 
        tqdm(users, desc="Downloading photos"), 
        output_dir, 
        verbose=args.verbose
    )
    
    result_msg = format_download_stats(successful, skipped, no_photo, failed)
    info(f"Profile photos: {result_msg} - saved to {output_dir}")


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Extract unique users from group message history and download profile photos.",
        epilog="Examples:\n  python user_export.py @group\n  python user_export.py @group --no-photos --limit 500\n  python user_export.py groups.txt --out ./results",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    get_args(parser)
    args = parser.parse_args()

    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass