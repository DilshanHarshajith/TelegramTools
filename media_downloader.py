"""
Media Downloader
----------------
Downloads media files (photos, videos, video messages, audio, documents, voice, stickers, GIFs)
from Telegram channels and groups. Supports concurrent downloads, resume on
restart, date filtering, type filtering, and auto join/leave.
"""

import os
import sys
import re
import asyncio
import argparse
from datetime import datetime, timezone
from typing import Optional

from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest, CheckChatInviteRequest
from telethon.tl.functions.account import UpdateNotifySettingsRequest
from telethon.tl.functions.folders import EditPeerFoldersRequest
from telethon.tl.types import (
    InputNotifyPeer,
    InputPeerNotifySettings,
    InputFolderPeer,
    MessageMediaDocument, MessageMediaPhoto,
    DocumentAttributeVideo, DocumentAttributeAudio,
    DocumentAttributeAnimated, DocumentAttributeSticker,
    ChatInviteAlready,
)
from telethon.errors import (
    UserAlreadyParticipantError,
    ChannelPrivateError,
    ChatAdminRequiredError,
    InviteHashExpiredError,
)
from tqdm import tqdm

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

def read_groups_from_file(file_path=None):
    path = file_path or _cfg.GROUP_FILE
    if not os.path.isfile(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

OUTPUT_DIR = os.getcwd()

# "video_message" = circular/round video notes (distinct from regular videos)
ALL_TYPES = {"photo", "video", "video_message", "document", "audio", "voice", "gif", "sticker"}


# ---------------------------------------------------------------------------
# CLI Arguments
# ---------------------------------------------------------------------------

def get_args(parser):
    parser.add_argument(
        "groups",
        nargs="*",
        help=(
            "Channels/groups to download from. Accepts: @username, t.me/link, "
            "invite link, numeric ID, or a file path with one entry per line."
        ),
    )
    parser.add_argument(
        "-n", "--limit",
        type=int,
        default=0,
        help="Max media files to download per group (0 = no limit).",
    )
    parser.add_argument(
        "-w", "--workers",
        type=int,
        default=4,
        help="Concurrent downloads (default: 4).",
    )
    parser.add_argument(
        "--out",
        type=str,
        help="Output directory (default: data/output/media_downloader).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan and count media without downloading.",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Ignore existing files and re-download everything.",
    )

    type_group = parser.add_argument_group(
        "media type filters",
        "Select which types to download. Combine freely. If none are set, all types are downloaded.",
    )
    type_group.add_argument("-p", "--photo",    action="store_true", help="Photos")
    type_group.add_argument("-v", "--video",    action="store_true", help="Videos")
    type_group.add_argument("--video-message",  action="store_true", help="Video messages (round/circular video notes)")
    type_group.add_argument("-d", "--document", action="store_true", help="Documents")
    type_group.add_argument("-a", "--audio",    action="store_true", help="Audio files")
    type_group.add_argument("--voice",          action="store_true", help="Voice messages")
    type_group.add_argument("--gif",            action="store_true", help="GIFs / animations")
    type_group.add_argument("--sticker",        action="store_true", help="Stickers")

    parser.add_argument(
        "--min-date",
        type=str,
        help="Only include media on or after this date (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS).",
    )
    parser.add_argument(
        "--max-date",
        type=str,
        help="Only include media on or before this date (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS).",
    )
    parser.add_argument(
        "--reverse",
        action="store_true",
        help="Scan from oldest messages first.",
    )
    parser.add_argument(
        "--hide-group",
        action="store_true",
        help=(
            "Mute and archive any channel/group that was joined by this tool "
            "while the tool is running. Has no effect on groups you were "
            "already a member of."
        ),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def build_wanted_types(args) -> set:
    requested = {
        name for name, flag in [
            ("photo",    args.photo),
            ("video",    args.video),
            ("document", args.document),
            ("audio",    args.audio),
            ("voice",    args.voice),
            ("gif",      args.gif),
            ("sticker",  args.sticker),
            ("video_message", args.video_message),
        ] if flag
    }
    return requested or ALL_TYPES


def parse_date(date_str: Optional[str]) -> Optional[datetime]:
    if not date_str:
        return None
    try:
        fmt = "%Y-%m-%d" if len(date_str) == 10 else "%Y-%m-%d %H:%M:%S"
        return datetime.strptime(date_str, fmt).replace(tzinfo=timezone.utc)
    except Exception as e:
        error(f"Invalid date '{date_str}': {e}")
        return None


def get_media_type(msg) -> Optional[str]:
    if not msg.media:
        return None
    if isinstance(msg.media, MessageMediaPhoto):
        return "photo"
    if isinstance(msg.media, MessageMediaDocument):
        doc = msg.media.document
        if not doc:
            return "document"
        for attr in doc.attributes:
            if isinstance(attr, DocumentAttributeSticker):
                return "sticker"
            if isinstance(attr, DocumentAttributeAnimated):
                return "gif"
            if isinstance(attr, DocumentAttributeVideo):
                # round_message=True → circular video note (video message)
                if getattr(attr, "round_message", False):
                    return "video_message"
                return "video"
            if isinstance(attr, DocumentAttributeAudio):
                return "voice" if getattr(attr, "voice", False) else "audio"
        return "document"
    return None


def _safe_file_id(msg) -> Optional[str]:
    """
    Return a string file ID for dedup/naming purposes.
    Falls back to the message ID string if Telethon's file.id raises
    AttributeError (e.g. PhotoSize objects without a .location in newer
    Telethon versions).
    """
    try:
        fid = msg.file.id
        if fid is not None:
            return str(fid)
    except AttributeError:
        pass
    return str(msg.id)


def get_dest_path(msg, chat_dir: str) -> Optional[str]:
    """
    Deterministic path: {msg_id}_{file_id}{ext}
    Falls back to {msg_id} alone when file_id cannot be resolved.
    """
    f = msg.file
    if not f:
        return None
    try:
        file_id = f.id
        if file_id is None:
            return None
        name = f"{msg.id}_{file_id}"
    except AttributeError:
        # f.id raises on certain PhotoSize objects that lack .location
        name = str(msg.id)
    ext = f.ext or ""
    return os.path.join(chat_dir, f"{name}{ext}")


def normalise_group(group_str: str):
    """Return int for numeric IDs, str for everything else."""
    s = group_str.strip()
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    return s


def safe_group_name(group_str: str) -> str:
    s = str(group_str).strip()
    s = re.sub(r'^(https?://)?(t\.me|telegram\.me|telegram\.dog)/', '', s, flags=re.IGNORECASE)
    s = re.sub(r'^(joinchat/|\+)', '', s)
    s = re.sub(r'^@', '', s)
    return re.sub(r'[/\\:*?"<>|]', "_", s)


def seed_seen_from_disk(chat_dir: str) -> set:
    """
    Build the dedup set from files already on disk.
    Supports both naming formats:
      - New: {msg_id}_{file_id}{ext}  → extracts file_id
      - Old: {file_id}{ext}           → extracts file_id directly
    """
    seen = set()
    if not os.path.isdir(chat_dir):
        return seen
    for fname in os.listdir(chat_dir):
        base = os.path.splitext(fname)[0]
        parts = base.split("_", 1)
        if len(parts) == 2 and parts[0].lstrip("-").isdigit():
            seen.add(parts[1])
        else:
            seen.add(base)
    return seen


# ---------------------------------------------------------------------------
# Join / Leave
# ---------------------------------------------------------------------------

async def resolve_entity(client, group_str):
    """
    Resolve a chat entity *without* joining it.

    Returns (entity, must_join) where:
      - entity     : the resolved Telegram entity, or None on failure
      - must_join  : True only when the link is a private invite hash and
                     the account is NOT yet a member — the only case where
                     joining is unavoidable before any content can be read.

    For public channels/groups the caller should always attempt to download
    first; joining is only a fallback if a ChannelPrivateError is raised.
    """
    target = normalise_group(group_str)

    invite_match = (
        re.search(r"t\.me/(?:\+|joinchat/)([\w-]+)", str(target))
        if isinstance(target, str) else None
    )

    if invite_match:
        invite_hash = invite_match.group(1)
        info(f"Invite hash detected: {invite_hash}")
        try:
            result = await client(CheckChatInviteRequest(invite_hash))
            if isinstance(result, ChatInviteAlready):
                # Already a member — entity is available, no join needed.
                info(f"Already a participant (invite link): {group_str}")
                return result.chat, False
            else:
                # ChatInvite — private link, not yet a member.
                # There is no way to read content without joining.
                info(f"Private invite — must join to access: {group_str}")
                return None, True
        except InviteHashExpiredError:
            error(f"Invite link has expired: {group_str}")
            return None, False
        except Exception as e:
            error(f"Could not check invite {group_str}: {e}")
            return None, False

    try:
        entity = await client.get_entity(target)
        if hasattr(entity, "left") and entity.left:
            info(f"Not a member of {group_str} — will attempt access without joining first.")
        else:
            info(f"Already a member of {group_str}.")
        return entity, False
    except Exception as e:
        error(f"Could not resolve {group_str}: {e}")
        return None, False


async def _do_join(client, group_str, entity=None):
    """
    Unconditionally join a chat.

    Returns (entity, joined_by_tool):
      - joined_by_tool is True  when this call actually joined the chat.
      - joined_by_tool is False when the account was already a member.
      - entity is None on failure.
    """
    target = normalise_group(group_str)

    invite_match = (
        re.search(r"t\.me/(?:\+|joinchat/)([\w-]+)", str(target))
        if isinstance(target, str) else None
    )

    if invite_match:
        invite_hash = invite_match.group(1)
        try:
            updates = await client(ImportChatInviteRequest(invite_hash))
            success(f"Joined via invite: {group_str}")
            return updates.chats[0], True
        except UserAlreadyParticipantError:
            info(f"Already a participant: {group_str}")
            # Re-check to retrieve the entity.
            try:
                result = await client(CheckChatInviteRequest(invite_hash))
                if isinstance(result, ChatInviteAlready):
                    return result.chat, False
            except Exception:
                pass
            return entity, False
        except Exception as e:
            error(f"Failed to join via invite {group_str}: {e}")
            return None, False

    try:
        if entity is None:
            entity = await client.get_entity(target)
        await client(JoinChannelRequest(entity))
        # Re-fetch so entity.left is updated.
        entity = await client.get_entity(target)
        success(f"Joined: {group_str}")
        return entity, True
    except UserAlreadyParticipantError:
        info(f"Already a participant: {group_str}")
        return entity, False
    except Exception as e:
        error(f"Could not join {group_str}: {e}")
        return None, False


async def leave_chat(client, entity, group_str):
    try:
        await client.delete_dialog(entity)
        success(f"Left {group_str}")
    except Exception as e:
        warning(f"Could not leave {group_str}: {e}")


async def mute_and_archive_chat(client, entity, group_str):
    """
    Mute all notifications and move the chat to the Archive folder (folder_id=1).

    Both operations are best-effort: a warning is printed on failure but
    execution continues normally.
    """
    # --- Mute ---
    try:
        input_peer = await client.get_input_entity(entity)
        await client(UpdateNotifySettingsRequest(
            peer=InputNotifyPeer(input_peer),
            settings=InputPeerNotifySettings(
                mute_until=2 ** 31 - 1,   # muted "forever" (year 2038)
                show_previews=False,
            ),
        ))
        info(f"Muted notifications for {group_str}.")
    except Exception as e:
        warning(f"Could not mute {group_str}: {e}")

    # --- Archive (move to folder 1) ---
    try:
        input_peer = await client.get_input_entity(entity)
        await client(EditPeerFoldersRequest(
            folder_peers=[
                InputFolderPeer(peer=input_peer, folder_id=1)
            ]
        ))
        info(f"Archived {group_str}.")
    except Exception as e:
        warning(f"Could not archive {group_str}: {e}")


# ---------------------------------------------------------------------------
# Download logic
# ---------------------------------------------------------------------------

async def _download_one(client, msg, dest, sem, pbar, stats):
    """Download a single message's media with semaphore-limited concurrency."""
    async with sem:
        try:
            file_path = await client.download_media(msg, file=dest)
            if file_path:
                stats["downloaded"] += 1
                stats["seen"].add(_safe_file_id(msg))
        except Exception as e:
            stats["failed"] += 1
            warning(f"Failed msg {msg.id}: {e}")
        finally:
            pbar.update(1)
            pbar.set_postfix(
                downloaded=stats["downloaded"],
                failed=stats["failed"],
                refresh=False,
            )


async def download_media_from_chat(client, entity, group_str, args, output_dir):
    chat_dir = os.path.join(output_dir, safe_group_name(group_str))
    os.makedirs(chat_dir, exist_ok=True)

    wanted_types = build_wanted_types(args)
    min_date_dt  = parse_date(args.min_date)
    max_date_dt  = parse_date(args.max_date)
    dry_run      = getattr(args, "dry_run", False)
    workers      = getattr(args, "workers", 4)
    no_resume    = getattr(args, "no_resume", False)

    info(f"Types: {', '.join(sorted(wanted_types))} | Source: {group_str} → {chat_dir}")
    if args.limit:
        info(f"Download cap: {args.limit} file(s)")
    if dry_run:
        info("Dry-run mode — nothing will be downloaded.")

    seen: set = set() if no_resume else seed_seen_from_disk(chat_dir)
    if seen and not no_resume:
        info(f"Resuming — {len(seen)} file(s) already on disk will be skipped.")

    # --- Collect matching messages first ---
    info("Scanning messages...")
    to_download = []
    scanned = 0
    iter_kwargs = {"reverse": True} if args.reverse else {}

    try:
        async for msg in client.iter_messages(entity, **iter_kwargs):
            scanned += 1

            # Date filter
            if msg.date:
                if min_date_dt and msg.date < min_date_dt:
                    if args.reverse:
                        continue
                    break
                if max_date_dt and msg.date > max_date_dt:
                    if args.reverse:
                        break
                    continue

            if not msg.media:
                continue

            m_type = get_media_type(msg)
            if m_type not in wanted_types:
                continue

            dest = get_dest_path(msg, chat_dir)
            if dest is None:
                continue

            file_id = _safe_file_id(msg)
            if file_id in seen:
                continue

            seen.add(file_id)  # mark immediately so re-posts in same scan are skipped
            to_download.append((msg, dest, file_id))

            if args.limit and len(to_download) >= args.limit:
                break

            if scanned % 200 == 0:
                print(f"\r  Scanned {scanned} messages, {len(to_download)} queued...", end="", flush=True)

    except KeyboardInterrupt:
        warning(f"\nScan interrupted — proceeding with {len(to_download)} queued.")

    print()
    info(f"Scanned {scanned} messages | Queued {len(to_download)} new file(s)")

    if dry_run:
        success(f"[Dry-run] Would download {len(to_download)} file(s) from {group_str}.")
        return

    if not to_download:
        success(f"Nothing new to download from {group_str}.")
        return

    # --- Concurrent downloads with progress bar ---
    stats = {"downloaded": 0, "failed": 0, "seen": seen}
    sem = asyncio.Semaphore(workers)

    with tqdm(total=len(to_download), unit="file", desc=safe_group_name(group_str)) as pbar:
        tasks = [
            asyncio.create_task(_download_one(client, msg, dest, sem, pbar, stats))
            for msg, dest, _ in to_download
        ]
        try:
            await asyncio.gather(*tasks)
        except KeyboardInterrupt:
            for t in tasks:
                t.cancel()
            warning(f"\nDownload interrupted — {stats['downloaded']} file(s) saved.")
            raise

    success(
        f"Done — {stats['downloaded']} downloaded, "
        f"{stats['failed']} failed | {group_str}"
    )


# ---------------------------------------------------------------------------
# Per-group orchestration
# ---------------------------------------------------------------------------

async def scrape_media(client, group, args, module_output):
    info(f"Processing: {group}")

    hide_group = getattr(args, "hide_group", False)
    joined_by_tool = False

    entity, must_join = await resolve_entity(client, group)

    # ── Case 1: private invite link where we are not yet a member ──────────
    # No content is accessible without joining, so join immediately.
    if must_join:
        entity, joined_by_tool = await _do_join(client, group)
        if not entity:
            error(f"Skipping {group} — could not join.")
            return
        if hide_group:
            await mute_and_archive_chat(client, entity, group)

    elif entity is None:
        error(f"Skipping {group} — could not resolve.")
        return

    # ── Case 2 & 3: entity resolved — try downloading without joining ──────
    # Public channels/groups allow iter_messages even when entity.left=True.
    # If access is denied (ChannelPrivateError / ChatAdminRequiredError) we
    # fall back to joining exactly once and retrying.
    try:
        await download_media_from_chat(client, entity, group, args, module_output)

    except (ChannelPrivateError, ChatAdminRequiredError) as exc:
        if joined_by_tool:
            # Already joined but still blocked — nothing more we can do.
            error(f"Access denied even after joining {group}: {exc}")
            return

        info(f"Access requires membership — joining {group}...")
        entity, joined_by_tool = await _do_join(client, group, entity)
        if not entity:
            error(f"Could not join {group}, skipping.")
            return

        if hide_group:
            await mute_and_archive_chat(client, entity, group)

        try:
            await download_media_from_chat(client, entity, group, args, module_output)
        except KeyboardInterrupt:
            raise

    except KeyboardInterrupt:
        raise

    finally:
        if joined_by_tool:
            info(f"Leaving {group} (was joined by tool)...")
            await leave_chat(client, entity, group)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def run(args):
    client = await connect_client()
    groups = list(args.groups or [])

    if len(groups) == 1 and os.path.isfile(groups[0]):
        groups = read_groups_from_file(groups[0])

    if not groups:
        error("No groups provided.")
        await client.disconnect()
        return

    module_output = args.out or os.path.join(OUTPUT_DIR, "media_downloader")
    os.makedirs(module_output, exist_ok=True)

    try:
        for group in groups:
            await scrape_media(client, group, args, module_output)
    except KeyboardInterrupt:
        warning("Interrupted by user.")
    finally:
        try:
            await client.disconnect()
        except Exception as e:
            warning(f"Error disconnecting: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Download media from Telegram channels and groups.",
        epilog=(
            "Examples:\n"
            "  python media_downloader.py @channel --video --photo\n"
            "  python media_downloader.py @channel --video-message\n"
            "  python media_downloader.py @channel -n 100 --dry-run\n"
            "  python media_downloader.py @channel --min-date 2024-01-01 --hide-group\n"
            "  python media_downloader.py groups.txt --audio --out ./downloads"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    get_args(parser)
    parsed = parser.parse_args()

    try:
        asyncio.run(run(parsed))
    except KeyboardInterrupt:
        pass