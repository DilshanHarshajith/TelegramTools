import os
import argparse
import sys
import asyncio
import re

import json
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

def get_args(parser):
    parser.add_argument(
        "-k", "--keyword",
        nargs="+",
        default=[],
        help="Keywords/phrases to search messages (one or more). Messages matching ANY keyword will be included."
    )
    parser.add_argument(
        "-l", "--limit",
        type=int,
        default=0,
        help="Message limit per group (0 = all messages)"
    )
    parser.add_argument(
        "--groups",
        nargs="*",
        help="Groups to process (overrides groups.txt). Can be group links or a file containing links, one per line."
    )
    parser.add_argument(
        "--user",
        type=str,
        help="Only include messages sent by this user (numeric ID or @username)"
    )
    parser.add_argument(
        "--replies",
        action="store_true",
        help="Include replies to matching messages in the JSON output"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show sender_id and a text snippet for each matching message"
    )
    parser.add_argument(
        "--out",
        type=str,
        help="Output directory (default: data/output/message_scraper)"
    )

async def run(args):
    client = await connect_client()
    
    # Groups are already processed by main.py, use args.groups directly
    groups = args.groups or []
    if not groups:
        error("No groups provided")
        await client.disconnect()
        return

    if not (args.user or args.keyword):
        error("At least one of --user or --keyword must be provided")
        await client.disconnect()
        return
    
    module_output = args.out if args.out else os.path.join(OUTPUT_DIR, "message_scraper")

    try:
        for group in groups:
            await scrape_group(
                client,
                group,
                args.keyword,
                args.limit,
                module_output,
                verbose=getattr(args, "verbose", False),
                include_replies=getattr(args, "replies", False),
                user_filter=getattr(args, "user", None),
            )
    finally:
        try:
            await client.disconnect()
        except Exception as e:
            warning(f"Error disconnecting client: {e}")

async def scrape_group(
    client,
    group,
    keywords,
    limit,
    module_output,
    verbose: bool = False,
    include_replies: bool = False,
    user_filter: str | None = None,
):
    s = str(group).strip()
    s = re.sub(r'^(https?://)?(t\.me|telegram\.me|telegram\.dog)/', '', s, flags=re.IGNORECASE)
    s = re.sub(r'^(joinchat/|\+)', '', s)
    s = re.sub(r'^@', '', s)
    group_safe = re.sub(r'[/\\:*?"<>|]', "_", s)
    output_dir = os.path.join(module_output, group_safe)
    os.makedirs(output_dir, exist_ok=True)

    info(f"Scraping {group} for {keywords if keywords else 'all messages'} (limit={limit or 'all'})")
    messages = []
    scanned = 0
    matched = 0

    try:
        async for msg in client.iter_messages(group, limit=limit or None):
            scanned += 1

            if not await should_include_message(msg, user_filter):
                continue

            # Match if no keywords provided OR if any keyword matches
            match = False
            if not keywords:
                match = True
            elif msg.message:
                msg_text_lower = msg.message.lower()
                for kw in keywords:
                    if kw.lower() in msg_text_lower:
                        match = True
                        break

            if match:
                matched += 1
                entry = {
                    "id": msg.id,
                    "sender_id": msg.sender_id,
                    "text": msg.message,
                }

                if include_replies:
                    replies_ctx = await collect_replies(client, group, msg)
                    entry.update(replies_ctx)

                messages.append(entry)

                if verbose:
                    snippet = msg.message.replace("\n", " ")[:80]
                    progress(f"{group} | sender_id={msg.sender_id} | \"{snippet}\"")

                if matched % 10 == 0:
                    progress(f"{group}: found {matched} matching messages after scanning {scanned}")

            # Periodic scan-only progress
            if scanned % 200 == 0:
                print(
                    f"[*] {group}: scanned {scanned} messages, matches so far: {matched}",
                    end="\r",
                    flush=True,
                )

    except KeyboardInterrupt:
        warning("\nCtrl+C detected, saving current progress for this group before exiting...")
        raise
    except Exception as e:
        error(f"Error scraping group {group}: {e}")
        return
    finally:
        print()
        path = os.path.join(output_dir, f"{group_safe}.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(messages, f, indent=4, ensure_ascii=False)
            info(f"Saved {len(messages)} messages (scanned {scanned}) to {path}")
        except Exception as e:
            error(f"Error saving messages to {path}: {e}")

async def should_include_message(msg, user_filter: str | None) -> bool:
    """
    Check if a message matches the user filter (if any).
    """
    if not user_filter:
        return True

    from_id = getattr(msg, "sender_id", None)
    
    # Numeric ID check
    if user_filter.isdigit() and from_id is not None:
        return str(from_id) == user_filter

    # Username check
    username_target = user_filter.lstrip("@").lower()
    try:
        sender = await msg.get_sender()
    except Exception:
        sender = None

    if sender is not None:
        uname = getattr(sender, "username", None)
        if uname and uname.lower() == username_target:
            return True
    
    return False

async def collect_replies(client, group, msg) -> dict:
    """
    Collect replies (children) and parent message for a given message.
    """
    result = {}
    
    # 1) Messages that reply TO this message (children)
    replies_data = []
    try:
        async for r in client.iter_messages(group, limit=REPLY_ITER_LIMIT if REPLY_ITER_LIMIT else 300):
            if getattr(r, "reply_to_msg_id", None) == msg.id:
                replies_data.append(
                    {
                        "id": r.id,
                        "sender_id": r.sender_id,
                        "text": r.message,
                    }
                )
    except Exception:
        pass

    if replies_data:
        result["replies"] = replies_data

    # 2) If this message itself is a reply to another message (parent)
    parent_id = getattr(msg, "reply_to_msg_id", None)
    if not parent_id and getattr(msg, "reply_to", None):
        parent_id = getattr(msg.reply_to, "reply_to_msg_id", None)

    if parent_id:
        try:
            parent = await client.get_messages(group, ids=parent_id)
            if parent:
                result["reply_to"] = {
                    "id": parent.id,
                    "sender_id": parent.sender_id,
                    "text": parent.message,
                }
        except Exception:
            pass
            
    return result


if __name__ == "__main__":
    
    parser = argparse.ArgumentParser(
        description="Search and export messages from Telegram groups by keyword or sender.",
        epilog="Examples:\n  python message_scraper.py --groups @channel -k bitcoin\n  python message_scraper.py --groups @channel -k bitcoin scam --replies\n  python message_scraper.py --groups groups.txt --user @someone\n  python message_scraper.py --groups @channel -k keyword --out ./results",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    get_args(parser)
    args = parser.parse_args()
    
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass