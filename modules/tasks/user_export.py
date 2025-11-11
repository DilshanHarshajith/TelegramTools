import os
import csv
from modules.utils.auth import connect_client
from modules.utils.group_utils import read_groups_from_file
from config import OUTPUT_DIR
from telethon.tl.types import User

def get_args(parser):
    parser.add_argument(
        "--download-photos",
        action="store_true",
        help="Download profile photos"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,   # 0 = all messages
        help="Maximum number of messages to scan per group (0 = all)"
    )

async def run(args):
    client = await connect_client()
    groups = args.groups or read_groups_from_file()
    module_output = os.path.join(OUTPUT_DIR, "user_export")

    for group in groups:
        await extract_visible_users(client, group, args.download_photos, args.limit, module_output)

    await client.disconnect()

async def extract_visible_users(client, group, download_photos=False, limit=0, module_output=None):
    group_safe = group.replace('/', '_')
    output_dir = os.path.join(module_output, group_safe)
    os.makedirs(output_dir, exist_ok=True)
    csv_file_path = os.path.join(output_dir, "visible_users.csv")

    # Load existing users to skip duplicates
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
        writer.writerow(["user_id", "username", "first_name", "last_name", "has_photo"])

    new_users = 0
    scanned = 0

    # Determine total messages to display progress
    total_messages = limit or await client.get_messages_count(group)
    async for msg in client.iter_messages(group, limit=limit or None):
        scanned += 1
        sender = msg.sender
        if not sender or not isinstance(sender, User):
            continue
        uid = str(sender.id)
        if uid in existing_uids:
            continue  # Skip already-exported users

        # New user
        has_photo = False
        if download_photos and sender.photo:
            filename = os.path.join(output_dir, f"{uid}.jpg")
            if not os.path.isfile(filename):  # Skip if photo already exists
                try:
                    await client.download_profile_photo(sender, file=filename)
                    has_photo = True
                except:
                    pass
            else:
                has_photo = True  # Already exists

        writer.writerow([uid, sender.username or "", sender.first_name or "", sender.last_name or "", has_photo])
        existing_uids.add(uid)
        new_users += 1

        # Print live progress
        print(f"\rScanning messages: {scanned}/{total_messages} | New users: {new_users}", end="")

    csv_file.close()
    print(f"\n[✓] Exported {new_users} new users from {group} to {output_dir}")
