import os
import csv
import asyncio
from telethon.tl.types import User
from telethon.errors import FloodWaitError
from modules.utils.auth import connect_client
from config import OUTPUT_DIR
from tqdm.asyncio import tqdm_asyncio

STOP = False  # For Ctrl+C handling

def get_args(parser):
    parser.add_argument(
        "--groups",
        nargs="*",
        help="Telegram group links or a file containing groups"
    )
    parser.add_argument(
        "--download-photos",
        action="store_true",
        help="Download profile photos"
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
        help="Show usernames next to progress bar"
    )

async def run(args):
    global STOP
    client = await connect_client()
    groups = args.groups
    module_output = os.path.join(OUTPUT_DIR, "user_export")
    os.makedirs(module_output, exist_ok=True)

    try:
        for group in groups:
            await extract_all_users(client, group, args, module_output)
    except KeyboardInterrupt:
        STOP = True
        print("\n[!] User interrupted, stopping...")
    finally:
        await client.disconnect()

async def extract_all_users(client, group, args, module_output):
    group_safe = group.replace('/', '_')
    output_dir = os.path.join(module_output, group_safe)
    os.makedirs(output_dir, exist_ok=True)
    csv_file_path = os.path.join(output_dir, "visible_users.csv")

    # Load existing users
    existing_uids = set()
    if os.path.isfile(csv_file_path):
        with open(csv_file_path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                existing_uids.add(row["user_id"])

    csv_exists = os.path.isfile(csv_file_path)
    csv_file = open(csv_file_path, "a", newline="", encoding="utf-8")
    writer = csv.writer(csv_file)
    if not csv_exists:
        writer.writerow(["user_id", "username", "first_name", "last_name"])

    print(f"[+] Processing group: {group}")

    new_users = []
    scanned = 0
    limit = args.limit or None

    async for msg in tqdm_asyncio(client.iter_messages(group, limit=limit), desc="Scanning messages"):
        if STOP:
            break
        scanned += 1
        sender = msg.sender
        if not sender or not isinstance(sender, User):
            continue
        uid = str(sender.id)
        if uid in existing_uids:
            continue
        new_users.append(sender)
        existing_uids.add(uid)
        if args.verbose:
            tqdm_asyncio.write(f"{sender.first_name or ''} | {uid}")

    # Save CSV first
    for sender in new_users:
        writer.writerow([
            str(sender.id),
            sender.username or "",
            sender.first_name or "",
            sender.last_name or "",
        ])
    csv_file.close()
    print(f"[✓] Collected {len(new_users)} new users from {group}")

    # Download photos if requested
    if args.download_photos and new_users:
        print("[*] Downloading profile photos...")
        from tqdm import tqdm
        for sender in tqdm(new_users, desc="Downloading photos"):
            filename = os.path.join(output_dir, f"{sender.username}_{sender.id}.jpg")
            if not os.path.isfile(filename) and sender.photo:
                try:
                    await client.download_profile_photo(sender, file=filename)
                except FloodWaitError as e:
                    print(f"[!] Flood wait {e.seconds}s. Waiting...")
                    await asyncio.sleep(e.seconds)
                except:
                    pass
        print(f"[✓] Export complete for {group} to {output_dir}")
