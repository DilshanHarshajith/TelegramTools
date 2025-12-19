import os
import asyncio
from telethon.tl.types import User
from modules.utils.auth import connect_client
from modules.utils.output import info, error, warning, success, progress
from modules.utils.csv_utils import read_existing_user_ids, write_user_to_csv, parse_user_ids_from_csv
from modules.utils.photo_utils import download_user_photo
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
        # If --users is provided, skip message scanning and just download photos
        if args.users:
            args.download_photos = True

            # If the argument points to an existing file, treat it as txt/csv
            if os.path.isfile(args.users):
                await download_photos_from_csv(client, args.users, args, module_output)
            else:
                # Treat the argument as an inline list of user IDs
                user_ids = parse_user_ids_from_inline(args.users)
                if not user_ids:
                    error("No valid user IDs found in --users argument")
                    return
                await download_photos_from_inline(client, user_ids, args, module_output)
        else:
            # Normal mode: scan messages from groups
            groups = args.groups
            if not groups:
                error("Either --groups or --users must be provided")
                return
            for group in groups:
                await extract_all_users(client, group, args, module_output)
    except KeyboardInterrupt:
        error("\nUser interrupted, stopping...")
    finally:
        try:
            await client.disconnect()
        except Exception as e:
            warning(f"Error disconnecting client: {e}")


def parse_user_ids_from_inline(inline_value: str):
    """
    Parse user IDs from an inline string passed to --users.
    Supports comma- or whitespace-separated numeric IDs.
    """
    if not inline_value:
        return []

    raw_parts = []
    if ',' in inline_value:
        raw_parts = inline_value.split(',')
    else:
        # Fallback: split on any whitespace
        raw_parts = inline_value.split()

    user_ids = [part.strip() for part in raw_parts if part.strip().isdigit()]

    # Deduplicate while preserving order
    seen = set()
    unique_ids = []
    for uid in user_ids:
        if uid not in seen:
            seen.add(uid)
            unique_ids.append(uid)
    return unique_ids

async def extract_all_users(client, group, args, module_output):
    group_safe = group.replace('/', '_')
    output_dir = os.path.join(module_output, group_safe)
    os.makedirs(output_dir, exist_ok=True)
    csv_file_path = os.path.join(output_dir, "visible_users.csv")

    # Load existing users using utility function
    existing_uids = read_existing_user_ids(csv_file_path)
    csv_exists = os.path.isfile(csv_file_path)
    info(f"Processing group: {group}")

    new_users = []
    scanned = 0
    limit = args.limit or None

    try:
        async for msg in tqdm_asyncio(client.iter_messages(group, limit=limit), desc="Scanning messages"):
            scanned += 1
            # Try to get sender - it might be None if not loaded
            sender = msg.sender
            if sender is None and msg.sender_id:
                try:
                    sender = await client.get_entity(msg.sender_id)
                except Exception:
                    if args.verbose:
                        tqdm_asyncio.write(f"[!] Could not fetch sender for message {msg.id}")
                    continue
            
            # If sender exists but username is missing, try multiple methods to get it
            if sender and isinstance(sender, User):
                username = getattr(sender, 'username', None)
                if not username:
                    # Try re-fetching by user ID directly (sometimes more reliable)
                    try:
                        full_sender = await client.get_entity(sender.id)
                        if isinstance(full_sender, User) and getattr(full_sender, 'username', None):
                            sender = full_sender
                    except Exception:
                        # If that fails, try using PeerUser
                        try:
                            from telethon.tl.types import PeerUser
                            peer = PeerUser(user_id=sender.id)
                            full_sender = await client.get_entity(peer)
                            if isinstance(full_sender, User) and getattr(full_sender, 'username', None):
                                sender = full_sender
                        except Exception:
                            pass  # Keep original sender if all re-fetch attempts fail
            
            if not sender or not isinstance(sender, User):
                if args.verbose and sender:
                    tqdm_asyncio.write(f"[!] Skipping non-User sender: {type(sender).__name__}")
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
        # Save CSV using utility function
        for sender in new_users:
            username = getattr(sender, 'username', None) or ""
            write_user_to_csv(
                csv_file_path,
                str(sender.id),
                username,
                sender.first_name or "",
                sender.last_name or "",
                csv_exists
            )
            csv_exists = True  # After first write, file exists
        
        success(f"Scanned {scanned} messages, found {len(new_users)} new users")
        success(f"Saved {len(new_users)} users to {csv_file_path}")

        # Download photos if requested
        if args.download_photos and new_users:
            progress("Downloading profile photos...")
            successful = 0
            skipped = 0
            no_photo = 0
            failed = 0
            
            for sender in tqdm(new_users, desc="Downloading photos"):
                success_flag, status = await download_user_photo(client, sender, output_dir, verbose=args.verbose)
                if success_flag:
                    successful += 1
                elif status == "skipped_exists":
                    skipped += 1
                elif status == "no_photo":
                    no_photo += 1
                else:
                    failed += 1
            
            result_msg = f"Profile photos: {successful} downloaded"
            if skipped > 0:
                result_msg += f", {skipped} skipped (already exist)"
            if no_photo > 0:
                result_msg += f", {no_photo} no photo"
            if failed > 0:
                result_msg += f", {failed} failed"
            success(f"{result_msg} - saved to {output_dir}")


async def download_photos_from_csv(client, csv_path, args, module_output):
    """
    Download profile photos for users specified in a CSV file.
    """
    info(f"Reading user IDs from CSV: {csv_path}")
    user_ids = parse_user_ids_from_csv(csv_path)
    
    if not user_ids:
        error("No valid user IDs found in CSV file")
        return
    
    info(f"Found {len(user_ids)} user IDs in CSV")
    
    # Create output directory based on CSV's parent directory (group name)
    # If CSV is in a subdirectory, use that subdirectory name
    csv_dir = os.path.dirname(csv_path)
    if csv_dir and csv_dir != module_output:
        # Extract the group name from the path
        group_dir_name = os.path.basename(csv_dir)
        output_dir = os.path.join(module_output, group_dir_name)
    else:
        # Fallback: use CSV filename without extension
        csv_basename = os.path.splitext(os.path.basename(csv_path))[0]
        output_dir = os.path.join(module_output, csv_basename)
    
    os.makedirs(output_dir, exist_ok=True)
    
    if not args.download_photos:
        warning("--no-photos set, skipping photo download")
        return
    
    progress("Fetching user entities and downloading photos...")
    
    successful = 0
    skipped = 0
    no_photo = 0
    failed = 0
    fetch_failed = 0
    
    for user_id in tqdm(user_ids, desc="Processing users"):
        try:
            # Fetch user entity
            user = await client.get_entity(int(user_id))
            if not isinstance(user, User):
                if args.verbose:
                    error(f"Skipping non-User entity: {user_id} ({type(user).__name__})")
                failed += 1
                continue
            
            # Download photo using utility function
            success_flag, status = await download_user_photo(client, user, output_dir, user_id=user_id, verbose=args.verbose)
            if success_flag:
                successful += 1
            elif status == "skipped_exists":
                skipped += 1
            elif status == "no_photo":
                no_photo += 1
            else:
                failed += 1
        except Exception as e:
            if args.verbose:
                error(f"Failed to fetch user {user_id}: {e}")
            fetch_failed += 1
    
    result_msg = f"Download complete: {successful} downloaded"
    if skipped > 0:
        result_msg += f", {skipped} skipped (already exist)"
    if no_photo > 0:
        result_msg += f", {no_photo} no photo"
    if failed > 0:
        result_msg += f", {failed} failed"
    if fetch_failed > 0:
        result_msg += f", {fetch_failed} fetch errors"
    success(result_msg)
    success(f"Photos saved to: {output_dir}")


async def download_photos_from_inline(client, user_ids, args, module_output):
    """
    Download profile photos for users specified directly via --users inline list.
    """
    if not user_ids:
        error("No valid user IDs provided for inline download")
        return

    info(f"Processing {len(user_ids)} user IDs from --users")

    # Use a generic directory for inline user lists
    output_dir = os.path.join(module_output, "manual_users")
    os.makedirs(output_dir, exist_ok=True)

    if not args.download_photos:
        warning("--no-photos set, skipping photo download")
        return

    progress("Fetching user entities and downloading photos...")

    successful = 0
    skipped = 0
    no_photo = 0
    failed = 0
    fetch_failed = 0

    for user_id in tqdm(user_ids, desc="Processing users"):
        try:
            user = await client.get_entity(int(user_id))
            if not isinstance(user, User):
                if args.verbose:
                    error(f"Skipping non-User entity: {user_id} ({type(user).__name__})")
                failed += 1
                continue

            success_flag, status = await download_user_photo(
                client, user, output_dir, user_id=user_id, verbose=args.verbose
            )
            if success_flag:
                successful += 1
            elif status == "skipped_exists":
                skipped += 1
            elif status == "no_photo":
                no_photo += 1
            else:
                failed += 1
        except Exception as e:
            if args.verbose:
                error(f"Failed to fetch user {user_id}: {e}")
            fetch_failed += 1

    result_msg = f"Download complete: {successful} downloaded"
    if skipped > 0:
        result_msg += f", {skipped} skipped (already exist)"
    if no_photo > 0:
        result_msg += f", {no_photo} no photo"
    if failed > 0:
        result_msg += f", {failed} failed"
    if fetch_failed > 0:
        result_msg += f", {fetch_failed} fetch errors"
    success(result_msg)
    success(f"Photos saved to: {output_dir}")
