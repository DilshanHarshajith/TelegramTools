import os
import argparse
import sys

import csv
import collections
from telethon import utils
from telethon.tl.types import PeerChannel, PeerUser, PeerChat
from telethon import TelegramClient, utils
from telethon.tl.types import PeerChannel, PeerUser, PeerChat
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
    CLI arguments for the origin_tracer module.
    """
    parser.add_argument(
        "--groups",
        nargs="*",
        help="Telegram group/channel links or usernames to analyze",
    )
    parser.add_argument(
        "--message-id",
        type=int,
        default=None,
        help="Specific Message ID to trace origin for (Single Message Mode)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Maximum number of messages to scan per group (0 = all, for Bulk Mode)"
    )
    parser.add_argument(
        "--min-count",
        type=int,
        default=1,
        help="Minimum number of forwards required to report a source (for Bulk Mode)"
    )
    parser.add_argument(
        "--out",
        type=str,
        help="Output directory (default: data/output/origin_tracer)"
    )


# ------------------------
# Main entry point
# ------------------------
async def run(args):
    """
    Trace origin of forwarded messages.
    Modes:
      1. Single Message Mode: If --message-id is set.
      2. Bulk Mode: If --message-id is NOT set.
    """
    client = await connect_client()
    groups = args.groups or read_groups_from_file()

    if not groups:
        error("No groups provided. Please specify --groups.")
        await client.disconnect()
        return

    module_output = args.out if args.out else os.path.join(OUTPUT_DIR, "origin_tracer")
    os.makedirs(module_output, exist_ok=True)

    try:
        if args.message_id:
            # Single Message Mode: We expect only one group
            if len(groups) > 1:
                warning("Multiple groups provided with --message-id. Only the first one will be checked.")
            
            await trace_single_message(client, groups[0], args.message_id)
        else:
            # Bulk Mode
            for group in groups:
                await trace_bulk_group(client, group, args, module_output)

    except KeyboardInterrupt:
        warning("\nInterrupted by user.")
    finally:
        await client.disconnect()


# ------------------------
# Single Message Logic
# ------------------------
async def trace_single_message(client, group, message_id):
    """
    Fetch a specific message and print its origin details.
    """
    info(f"Tracing Message ID {message_id} in {group}...")
    try:
        msgs = await client.get_messages(group, ids=[message_id])
        if not msgs:
            error(f"Message {message_id} not found in {group}.")
            return
        
        msg = msgs[0]
        if not msg: # Depending on permissions, might return None in list
            error(f"Message {message_id} is empty (deleted or inaccessible).")
            return

        if not msg.fwd_from:
            print(f"[-] Message {message_id} is NOT a forward.")
            return

        # Resolve Origin
        origin_info = await resolve_forward_header(client, msg.fwd_from)
        
        print("\n" + "="*30)
        print(f" MESSAGE {message_id} ORIGIN REPORT")
        print("="*30)
        print(f" Source Name  : {origin_info['name']}")
        print(f" Source ID    : {origin_info['id']}")
        print(f" Source Type  : {origin_info['type']}")
        if msg.fwd_from.saved_from_peer:
             saved_from = await resolve_peer(client, msg.fwd_from.saved_from_peer)
             print(f" Saved From   : {saved_from['name']} ({saved_from['id']})")
        print(f" Date         : {msg.fwd_from.date}")
        print("="*30 + "\n")

    except Exception as e:
        error(f"Failed to trace message: {e}")


# ------------------------
# Bulk Mode Logic
# ------------------------
async def trace_bulk_group(client, group, args, module_output):
    """
    Scan group history and build a stats report of top content sources.
    """
    info(f"Analyzing usage in: {group}")
    
    # Store counts: SourceID -> Count
    source_counts = collections.Counter()
    # Cache known info: SourceID -> {name, type, id}
    source_info_cache = {}

    total = args.limit or "All"
    scanned = 0
    fwd_count = 0

    group_entity = await client.get_entity(group)
    
    async for msg in client.iter_messages(group_entity, limit=args.limit or None):
        scanned += 1
        if scanned % 100 == 0:
            print(f"\rScanning: {scanned}...", end="")

        if msg.fwd_from:
            fwd_count += 1
            # Determine Main Source Peer
            # fwd_from.from_id is the original author/channel
            # fwd_from.from_name is used if string name (hidden user)
            
            s_id = None
            s_name = "Unknown"
            
            if msg.fwd_from.from_id:
                s_id = utils.get_peer_id(msg.fwd_from.from_id)
                # We defer resolving the name until the end to save network calls
            elif msg.fwd_from.from_name:
                s_name = msg.fwd_from.from_name
                s_id = s_name # Use name as ID for Hidden Users
            
            if s_id:
                source_counts[s_id] += 1
                if s_id not in source_info_cache:
                    if isinstance(s_id, int):
                         source_info_cache[s_id] = {"id": s_id, "name": f"Pending...{s_id}", "type": "Entity"}
                    else:
                         source_info_cache[s_id] = {"id": "N/A", "name": s_name, "type": "HiddenUser"}

    print(f"\rFinished. Scanned: {scanned}. Forwards Found: {fwd_count}")
    
    if not source_counts:
        warning("No forwarded messages found.")
        return

    # Resolve Entities for top keys
    # To optimize, we can resolve them in batch or just get_entity
    progress("Resolving source names...")
    
    final_data = []
    
    for s_id, count in source_counts.most_common():
        if count < args.min_count:
            continue

        raw_info = source_info_cache.get(s_id)
        
        # If it's an integer ID, try to resolve real name now
        if isinstance(s_id, int):
            try:
                entity = await client.get_entity(s_id)
                name = utils.get_display_name(entity)
                e_type = "User" if isinstance(entity, PeerUser) or (hasattr(entity, 'bot') and entity.bot) else "Channel/Chat"
                # Refine type based on class
                if hasattr(entity, 'broadcast') and entity.broadcast: e_type = "Channel"
                elif hasattr(entity, 'megagroup') and entity.megagroup: e_type = "Supergroup"
                
                raw_info['name'] = name
                raw_info['type'] = e_type
            except Exception:
                raw_info['name'] = f"Unknown Entity ({s_id})"
                raw_info['type'] = "Unknown"

        final_data.append({
            "count": count,
            "percent": f"{(count/fwd_count)*100:.1f}%",
            "name": raw_info['name'],
            "id": raw_info['id'],
            "type": raw_info['type']
        })

    # Export CSV
    safe_name = str(utils.get_display_name(group_entity)).replace("/", "_")
    csv_path = os.path.join(module_output, f"origin_report_{safe_name}.csv")
    
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["Rank", "Count", "Percent", "Name", "ID", "Type"])
        writer.writeheader()
        for idx, row in enumerate(final_data, 1):
            writer.writerow({
                "Rank": idx,
                "Count": row['count'],
                "Percent": row['percent'],
                "Name": row['name'],
                "ID": row['id'],
                "Type": row['type']
            })
            
    info(f"Report saved to: {csv_path}")

# ------------------------
# Utils
# ------------------------
async def resolve_forward_header(client, fwd_header):
    """
    Helper to extract readable info from a MessageFwdHeader
    """
    data = {"name": "Unknown", "id": "N/A", "type": "Unknown"}
    
    if fwd_header.from_id:
        p_info = await resolve_peer(client, fwd_header.from_id)
        data.update(p_info)
    elif fwd_header.from_name:
        data["name"] = fwd_header.from_name
        data["type"] = "Hidden User"
    
    return data

async def resolve_peer(client, peer):
    """
    Resolve a Peer object to simple dict
    """
    try:
        entity = await client.get_entity(peer)
        return {
            "name": utils.get_display_name(entity),
            "id": entity.id,
            "type": type(entity).__name__
        }
    except:
        return {"name": "Unresolvable", "id": utils.get_peer_id(peer), "type": "Unknown"}


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Trace the original source of forwarded messages in Telegram groups.",
        epilog="Examples:\n  python origin_tracer.py --groups @channel\n  python origin_tracer.py --groups @channel --message-id 42\n  python origin_tracer.py --groups @channel --limit 1000 --min-count 3",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    get_args(parser)
    args = parser.parse_args()

    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass