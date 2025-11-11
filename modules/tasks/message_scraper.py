import os
import json
from modules.utils.auth import connect_client
from modules.utils.group_utils import read_groups_from_file
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
        help="Message limit per group"
    )

async def run(args):
    client = await connect_client()
    groups = args.groups or read_groups_from_file()
    module_output = os.path.join(OUTPUT_DIR, "message_scraper")

    for group in groups:
        await scrape_group(client, group, args.keyword, args.limit, module_output)

    await client.disconnect()

async def scrape_group(client, group, keyword, limit, module_output):
    group_safe = group.replace('/', '_')
    output_dir = os.path.join(module_output, group_safe)
    os.makedirs(output_dir, exist_ok=True)

    print(f"Scraping {group} for '{keyword}' (limit={limit})")
    messages = []
    async for msg in client.iter_messages(group, limit=limit):
        if msg.message and keyword.lower() in msg.message.lower():
            messages.append({"id": msg.id, "sender_id": msg.sender_id, "text": msg.message})

    path = os.path.join(output_dir, f"{group_safe}.json")
    with open(path, "w") as f:
        json.dump(messages, f, indent=4)
    print(f"[+] Saved {len(messages)} messages to {path}")
