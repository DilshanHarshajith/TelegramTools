"""
Universal Task Module Template
------------------------------
Instructions:
1. Copy this file and rename it for a new task module.
2. Implement your logic in process_item().
3. The module automatically handles:
   - Async Telegram client connection
   - Groups from CLI (file or direct links)
   - Per-group output folders
   - Optional --limit
   - Live progress tracking
"""

import os
from modules.utils.auth import connect_client
from modules.utils.group_utils import read_groups_from_file
from config import OUTPUT_DIR
from telethon.tl.types import User  # or other types your module needs

# ------------------------
# CLI Arguments
# ------------------------
def get_args(parser):
    """
    Add module-specific CLI arguments here
    Example:
        parser.add_argument("--keyword", type=str, help="Search keyword")
    """
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Maximum number of messages/items to scan per group (0 = all)"
    )
    parser.add_argument(
        "--example",
        type=str,
        default="default",
        help="Example argument"
    )


# ------------------------
# Main entry point
# ------------------------
async def run(args):
    client = await connect_client()
    groups = args.groups or read_groups_from_file()
    module_output = os.path.join(OUTPUT_DIR, "module_template")  # adjust name

    for group in groups:
        await process_group(client, group, args, module_output)

    await client.disconnect()


# ------------------------
# Process each group
# ------------------------
async def process_group(client, group, args, module_output):
    """
    Handles per-group output folder, scanning, and progress display.
    Calls process_item() for each message/item.
    """
    group_safe = group.replace("/", "_")
    output_dir = os.path.join(module_output, group_safe)
    os.makedirs(output_dir, exist_ok=True)

    existing_items = set()
    total_messages = args.limit or await client.get_messages_count(group)
    scanned = 0
    new_items = 0

    async for msg in client.iter_messages(group, limit=args.limit or None):
        scanned += 1
        added = await process_item(client, msg, output_dir, args, existing_items)
        if added:
            new_items += 1

        # Live progress display
        print(f"\rScanning messages: {scanned}/{total_messages} | New items: {new_items}", end="")

    print(f"\n[✓] Processed {new_items} new items from {group} to {output_dir}")


# ------------------------
# Module-specific logic
# ------------------------
async def process_item(client, msg, output_dir, args, existing_items):
    """
    Replace this with your module logic.
    Return True if a new item was created (for progress counter), False otherwise.
    Examples:
    - Saving messages to CSV/JSON
    - Downloading media
    - Filtering by keyword
    """
    # Example: no-op (override this in your module)
    return False
