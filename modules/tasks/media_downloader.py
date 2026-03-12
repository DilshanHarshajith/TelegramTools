"""
Media Downloader
----------------
Downloads media files (photos, videos, audio, documents, voice, stickers, GIFs)
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

# Add project root to sys.path if running as standalone script
if __name__ == "__main__":
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.errors import UserAlreadyParticipantError
from telethon.tl.types import (
    MessageMediaDocument, MessageMediaPhoto,
    DocumentAttributeVideo, DocumentAttributeAudio,
    DocumentAttributeAnimated, DocumentAttributeSticker,
)
from tqdm import tqdm

from telethon import TelegramClient
import config as _cfg
from config import API_ID, API_HASH, SESSION_NAME

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
    from config import GROUP_FILE
    path = file_path or GROUP_FILE
    if not os.path.isfile(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

OUTPUT_DIR = os.getcwd()

ALL_TYPES = {"photo", "video", "document", "audio", "voice", "gif", "sticker"}


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
                return "video"
            if isinstance(attr, DocumentAttributeAudio):
                return "voice" if getattr(attr, "voice", False) else "audio"
        return "document"
    return None


def get_dest_path(msg, chat_dir: str) -> Optional[str]:
    """
    Deterministic path: {msg_id}_{file_id}{ext}
    - msg_id  : message ID (human-readable order)
    - file_id : Telegram file ID (stable across forwards/reposts)
    """
    f = msg.file
    if not f or not f.id:
        return None
    ext = f.ext or ""
    return os.path.join(chat_dir, f"{msg.id}_{f.id}{ext}")


def normalise_group(group_str: str):
    """Return int for numeric IDs, str for everything else."""
    s = group_str.strip()
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    return s


def safe_group_name(group_str: str) -> str:
    return re.sub(r'[/\\:*?"<>|]', "_", str(group_str))


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

async def join_chat(client, group_str):
    """Join a chat if needed. Returns (entity, joined_by_tool)."""
    joined_by_tool = False
    target = normalise_group(group_str)

    invite_match = (
        re.search(r"t\.me/(?:\+|joinchat/)([\w-]+)", str(target))
        if isinstance(target, str) else None
    )

    if invite_match:
        invite_hash = invite_match.group(1)
        info(f"Invite hash detected: {invite_hash}")
        try:
            updates = await client(ImportChatInviteRequest(invite_hash))
            joined_by_tool = True
            success(f"Joined via invite: {group_str}")
            return updates.chats[0], joined_by_tool
        except UserAlreadyParticipantError:
            info(f"Already a participant: {group_str}")
        except Exception as e:
            error(f"Failed to join via invite {group_str}: {e}")
            return None, False

    try:
        entity = await client.get_entity(target)
        if hasattr(entity, "left") and entity.left:
            info(f"Not a member of {group_str} — joining...")
            await client(JoinChannelRequest(entity))
            joined_by_tool = True
            success(f"Joined: {group_str}")
        else:
            info(f"Already a member of {group_str}.")
        return entity, joined_by_tool
    except Exception as e:
        error(f"Could not resolve or join {group_str}: {e}")
        return None, False


async def leave_chat(client, entity, group_str):
    try:
        await client.delete_dialog(entity)
        success(f"Left {group_str}")
    except Exception as e:
        warning(f"Could not leave {group_str}: {e}")


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
                stats["seen"].add(str(msg.file.id))
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

            file_id = str(msg.file.id)
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
    entity, joined_by_tool = await join_chat(client, group)

    if not entity:
        error(f"Skipping {group} — could not resolve or join.")
        return

    try:
        await download_media_from_chat(client, entity, group, args, module_output)
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
    parser = argparse.ArgumentParser(description="Telegram Media Downloader")
    get_args(parser)
    parsed = parser.parse_args()

    try:
        asyncio.run(run(parsed))
    except KeyboardInterrupt:
        pass