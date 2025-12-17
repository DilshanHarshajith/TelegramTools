import os
import json
from modules.utils.auth import connect_client
from modules.utils.output import info, error, success, warning, progress
from config import OUTPUT_DIR

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

            # If a user filter is provided, skip messages not from that user
            if user_filter:
                from_id = getattr(msg, "sender_id", None)
                matches_user = False

                # Numeric ID filter
                if user_filter.isdigit() and from_id is not None:
                    if str(from_id) == user_filter:
                        matches_user = True
                else:
                    # Username filter (e.g. "user" or "@user")
                    username_target = user_filter.lstrip("@").lower()
                    try:
                        sender = await msg.get_sender()
                    except Exception:
                        sender = None
                    if sender is not None:
                        uname = getattr(sender, "username", None)
                        if uname and uname.lower() == username_target:
                            matches_user = True

                if not matches_user:
                    continue

            if msg.message and keyword.lower() in msg.message.lower() or keyword == "":
                matched += 1
                entry = {
                    "id": msg.id,
                    "sender_id": msg.sender_id,
                    "text": msg.message,
                }

                # Optionally collect replies for this matching message
                if include_replies:
                    # 1) Messages that reply TO this message (children)
                    replies_data = []
                    try:
                        async for r in client.iter_messages(group, limit=300):
                            if getattr(r, "reply_to_msg_id", None) == msg.id:
                                replies_data.append(
                                    {
                                        "id": r.id,
                                        "sender_id": r.sender_id,
                                        "text": r.message,
                                    }
                                )
                    except Exception:
                        # Silently ignore reply collection errors, keep main result intact
                        pass

                    if replies_data:
                        entry["replies"] = replies_data

                    # 2) If this message itself is a reply to another message (parent)
                    parent_id = getattr(msg, "reply_to_msg_id", None)
                    if not parent_id and getattr(msg, "reply_to", None):
                        parent_id = getattr(msg.reply_to, "reply_to_msg_id", None)

                    if parent_id:
                        try:
                            parent = await client.get_messages(group, ids=parent_id)
                            if parent:
                                entry["reply_to"] = {
                                    "id": parent.id,
                                    "sender_id": parent.sender_id,
                                    "text": parent.message,
                                }
                        except Exception:
                            # If parent fetch fails, just skip it
                            pass

                messages.append(entry)

                if verbose:
                    # Show sender_id and a short snippet of the text (first 80 chars)
                    snippet = msg.message.replace("\n", " ")[:80]
                    info(f"{group} | sender_id={msg.sender_id} | \"{snippet}\"")

                # Show progress for matches every 10 messages found
                if matched % 10 == 0:
                    progress(f"{group}: found {matched} matching messages after scanning {scanned}")

            # Periodic scan-only progress: update a single line in-place to avoid scroll spam
            if scanned % 200 == 0:
                print(
                    f"[*] {group}: scanned {scanned} messages, matches so far: {matched}",
                    end="\r",
                    flush=True,
                )

    except KeyboardInterrupt:
        warning("\nCtrl+C detected, saving current progress for this group before exiting...")
        # Re-raise so the caller (and main) can stop processing further groups
        raise
    except Exception as e:
        error(f"Error scraping group {group}: {e}")
        return
    finally:
        # Ensure we end any in-place progress line with a newline before final messages
        print()
        path = os.path.join(output_dir, f"{group_safe}.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(messages, f, indent=4, ensure_ascii=False)
            success(f"Saved {len(messages)} messages (scanned {scanned}) to {path}")
        except Exception as e:
            error(f"Error saving messages to {path}: {e}")
