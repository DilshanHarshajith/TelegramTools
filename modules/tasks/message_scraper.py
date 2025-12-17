import os
import json
from modules.utils.auth import connect_client
from modules.utils.output import info, error, success
from config import OUTPUT_DIR

def get_args(parser):
    parser.add_argument(
        "-k", "--keyword",
        type=str,
        required=True,
        help="Keyword to search messages"
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

async def run(args):
    client = await connect_client()
    
    # Groups are already processed by main.py, use args.groups directly
    groups = args.groups or []
    if not groups:
        error("No groups provided")
        await client.disconnect()
        return
    
    module_output = os.path.join(OUTPUT_DIR, "message_scraper")

    try:
        for group in groups:
            await scrape_group(client, group, args.keyword, args.limit, module_output)
    finally:
        try:
            await client.disconnect()
        except Exception as e:
            error(f"Error disconnecting client: {e}")

async def scrape_group(client, group, keyword, limit, module_output):
    group_safe = group.replace('/', '_')
    output_dir = os.path.join(module_output, group_safe)
    os.makedirs(output_dir, exist_ok=True)

    info(f"Scraping {group} for '{keyword}' (limit={limit or 'all'})")
    messages = []

    try:
        async for msg in client.iter_messages(group, limit=limit or None):
            if msg.message and keyword.lower() in msg.message.lower():
                messages.append({
                    "id": msg.id,
                    "sender_id": msg.sender_id,
                    "text": msg.message
                })
    except Exception as e:
        error(f"Error scraping group {group}: {e}")
        return

    path = os.path.join(output_dir, f"{group_safe}.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(messages, f, indent=4, ensure_ascii=False)
        success(f"Saved {len(messages)} messages to {path}")
    except Exception as e:
        error(f"Error saving messages to {path}: {e}")
