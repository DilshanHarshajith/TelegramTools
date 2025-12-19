import os
import asyncio
from telethon.tl.types import User
from modules.utils.auth import connect_client
from modules.utils.output import info, error, warning, success, progress
from modules.utils.csv_utils import read_existing_user_ids, write_user_to_csv, parse_user_ids_from_csv
from modules.utils.photo_utils import download_photos_batch, format_download_stats
from modules.utils.user_utils import parse_user_ids_string, fetch_full_user
from config import OUTPUT_DIR
from tqdm.asyncio import tqdm_asyncio
from tqdm import tqdm

def get_args(parser):
    parser.add_argument(
        "--groups",
        nargs="*",
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
        "--users",
        type=str,
        help="User IDs source: either a txt/csv file path (like the exported CSV) or a quoted, comma-separated list of user IDs. When provided, message scanning is skipped."
    )

async def run(args):
    client = await connect_client()
    module_output = os.path.join(OUTPUT_DIR, "user_export")
    os.makedirs(module_output, exist_ok=True)

    try:
        if args.users:
            # Mode: Download photos for specific users (no scanning)
            args.download_photos = True
            await handle_users_mode(client, args.users, args, module_output)
        else:
            # Mode: Scan messages from groups
            if not args.groups:
                error("Either --groups or --users must be provided")
                return
            
            for group in args.groups:
                await scan_group_messages(client, group, args, module_output)

    except KeyboardInterrupt:
        error("\nUser interrupted, stopping...")
    finally:
        try:
            await client.disconnect()
        except Exception as e:
            warning(f"Error disconnecting client: {e}")


async def handle_users_mode(client, users_arg, args, module_output):
    """
    Handle the flow when --users is provided (file or inline).
    """
    user_ids = []
    output_dir = ""

    if os.path.isfile(users_arg):
        # Case 1: File input (CSV/TXT)
        info(f"Reading user IDs from file: {users_arg}")
        user_ids = parse_user_ids_from_csv(users_arg)
        
        # Determine output directory based on file location/name
        csv_dir = os.path.dirname(users_arg)
        # If the file is in a subdirectory of our module output, preserve that structure
        # Otherwise use the filename
        if csv_dir and os.path.commonpath([csv_dir, module_output]) == module_output and csv_dir != module_output:
             # It's already inside module_output, use that dir
             output_dir = csv_dir
        else:
            # Use filename as folder name
            basename = os.path.splitext(os.path.basename(users_arg))[0]
            output_dir = os.path.join(module_output, basename)
            
    else:
        # Case 2: Inline string
        user_ids = parse_user_ids_string(users_arg)
        output_dir = os.path.join(module_output, "manual_users")

    if not user_ids:
        error("No valid user IDs found in --users argument")
        return

    info(f"Found {len(user_ids)} unique user IDs")
    os.makedirs(output_dir, exist_ok=True)
    await process_photo_downloads(client, user_ids, output_dir, args)


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
    group_safe = group.replace('/', '_')
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


async def process_photo_downloads(client, users_or_ids, output_dir, args):
    """
    Download photos for a list of Users or user IDs.
    """
    if not args.download_photos:
        warning("--no-photos set, skipping photo download")
        return

    users_to_download = []
    
    # Check if input is list of IDs (strings/ints) or User objects
    first_item = users_or_ids[0] if users_or_ids else None
    
    if isinstance(first_item, (str, int)):
        # Need to fetch entities first
        progress(f"Fetching entities for {len(users_or_ids)} users...")
        fetch_failed = 0
        for user_id in tqdm(users_or_ids, desc="Fetching entities"):
            try:
                user = await client.get_entity(int(user_id))
                if isinstance(user, User):
                    users_to_download.append(user)
                else:
                    if args.verbose:
                        error(f"Skipping non-User entity: {user_id}")
            except Exception as e:
                if args.verbose:
                    error(f"Failed to fetch user {user_id}: {e}")
                fetch_failed += 1
                
        if fetch_failed > 0:
            warning(f"Failed to fetch {fetch_failed} users")
    else:
        # Already User objects
        users_to_download = users_or_ids

    if not users_to_download:
        warning("No valid users to download photos for.")
        return

    progress(f"Starting download for {len(users_to_download)} users...")
    
    successful, skipped, no_photo, failed = await download_photos_batch(
        client, 
        tqdm(users_to_download, desc="Downloading photos"), 
        output_dir, 
        verbose=args.verbose
    )
    
    result_msg = format_download_stats(successful, skipped, no_photo, failed)
    success(f"Profile photos: {result_msg} - saved to {output_dir}")

