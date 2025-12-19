import os
import json
from modules.utils.auth import connect_client
from modules.utils.output import info, error, success, warning, progress
from config import OUTPUT_DIR, REPLY_ITER_LIMIT

def get_args(parser):
    parser.add_argument(
        "-k", "--keyword",
        type=str,
        default="",
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
    parser.add_argument(
        "--user",
        type=str,
        help="Only include messages sent by this user (numeric ID or @username)"
    )
    parser.add_argument(
        "--replies",
        action="store_true",
        help="Include replies to matching messages in the JSON output"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show sender_id and a text snippet for each matching message"
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
            await scrape_group(
                client,
                group,
                args.keyword,
                args.limit,
                module_output,
                verbose=getattr(args, "verbose", False),
                include_replies=getattr(args, "replies", False),
                user_filter=getattr(args, "user", None),
            )
    finally:
        try:
            await client.disconnect()
        except Exception as e:
            warning(f"Error disconnecting client: {e}")

async def scrape_group(
    client,
    group,
    keyword,
    limit,
    module_output,
    verbose: bool = False,
    include_replies: bool = False,
    user_filter: str | None = None,
):
    group_safe = group.replace('/', '_')
    output_dir = os.path.join(module_output, group_safe)
    os.makedirs(output_dir, exist_ok=True)

    info(f"Scraping {group} for '{keyword}' (limit={limit or 'all'})")
    messages = []
    scanned = 0
    matched = 0

    try:
        async for msg in client.iter_messages(group, limit=limit or None):
            scanned += 1

            if not await should_include_message(msg, user_filter):
                continue

            if msg.message and (keyword.lower() in msg.message.lower() or keyword == ""):
                matched += 1
                entry = {
                    "id": msg.id,
                    "sender_id": msg.sender_id,
                    "text": msg.message,
                }

                if include_replies:
                    replies_ctx = await collect_replies(client, group, msg)
                    entry.update(replies_ctx)

                messages.append(entry)

                if verbose:
                    snippet = msg.message.replace("\n", " ")[:80]
                    info(f"{group} | sender_id={msg.sender_id} | \"{snippet}\"")

                if matched % 10 == 0:
                    progress(f"{group}: found {matched} matching messages after scanning {scanned}")

            # Periodic scan-only progress
            if scanned % 200 == 0:
                print(
                    f"[*] {group}: scanned {scanned} messages, matches so far: {matched}",
                    end="\r",
                    flush=True,
                )

    except KeyboardInterrupt:
        warning("\nCtrl+C detected, saving current progress for this group before exiting...")
        raise
    except Exception as e:
        error(f"Error scraping group {group}: {e}")
        return
    finally:
        print()
        path = os.path.join(output_dir, f"{group_safe}.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(messages, f, indent=4, ensure_ascii=False)
            success(f"Saved {len(messages)} messages (scanned {scanned}) to {path}")
        except Exception as e:
            error(f"Error saving messages to {path}: {e}")

async def should_include_message(msg, user_filter: str | None) -> bool:
    """
    Check if a message matches the user filter (if any).
    """
    if not user_filter:
        return True

    from_id = getattr(msg, "sender_id", None)
    
    # Numeric ID check
    if user_filter.isdigit() and from_id is not None:
        return str(from_id) == user_filter

    # Username check
    username_target = user_filter.lstrip("@").lower()
    try:
        sender = await msg.get_sender()
    except Exception:
        sender = None

    if sender is not None:
        uname = getattr(sender, "username", None)
        if uname and uname.lower() == username_target:
            return True
    
    return False

async def collect_replies(client, group, msg) -> dict:
    """
    Collect replies (children) and parent message for a given message.
    """
    result = {}
    
    # 1) Messages that reply TO this message (children)
    replies_data = []
    try:
        async for r in client.iter_messages(group, limit=REPLY_ITER_LIMIT if REPLY_ITER_LIMIT else 300):
            if getattr(r, "reply_to_msg_id", None) == msg.id:
                replies_data.append(
                    {
                        "id": r.id,
                        "sender_id": r.sender_id,
                        "text": r.message,
                    }
                )
    except Exception:
        pass

    if replies_data:
        result["replies"] = replies_data

    # 2) If this message itself is a reply to another message (parent)
    parent_id = getattr(msg, "reply_to_msg_id", None)
    if not parent_id and getattr(msg, "reply_to", None):
        parent_id = getattr(msg.reply_to, "reply_to_msg_id", None)

    if parent_id:
        try:
            parent = await client.get_messages(group, ids=parent_id)
            if parent:
                result["reply_to"] = {
                    "id": parent.id,
                    "sender_id": parent.sender_id,
                    "text": parent.message,
                }
        except Exception:
            pass
            
    return result
