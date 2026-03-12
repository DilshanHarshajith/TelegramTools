import os
import sys
import json
import asyncio
import argparse
from datetime import datetime
from telethon.tl import functions
from telethon.tl.types import User, UserStatusOnline, UserStatusOffline, UserStatusRecently, UserStatusLastWeek, UserStatusLastMonth

# Add project root to sys.path if running as standalone script
if __name__ == "__main__":
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

from telethon import TelegramClient
from telethon.errors import UsernameInvalidError, UsernameNotOccupiedError, PeerIdInvalidError
from telethon.tl.types import InputPhoneContact
from telethon.tl.functions import contacts as contacts_functions
import config as _cfg
from config import API_ID, API_HASH, SESSION_NAME, DEFAULT_LIMIT

def info(message): print(f"[*] {message}") if _cfg.VERBOSE or _cfg.INFO else None
def error(message): print(f"[!] {message}") if _cfg.VERBOSE or _cfg.ERROR else None
def warning(message): print(f"[!] {message}") if _cfg.VERBOSE or _cfg.WARNING else None
def success(message): print(f"[✓] {message}") if _cfg.VERBOSE or _cfg.SUCCESS else None

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

def parse_user_inputs(input_str):
    if not input_str:
        return []
    raw_parts = input_str.replace(',', ' ').split()
    collected = []
    seen = set()
    for part in raw_parts:
        normalized = part.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            collected.append(normalized)
    return collected

async def resolve_phone(client, phone):
    phone = phone.strip().replace(" ", "").replace("-", "")
    try:
        try:
            entity = await client.get_entity(phone)
            if isinstance(entity, User):
                return entity
        except Exception:
            pass
        contact = InputPhoneContact(client_id=0, phone=phone, first_name="TelegramTools", last_name="Search")
        result = await client(contacts_functions.ImportContactsRequest(contacts=[contact]))
        if result.users:
            imported_user = result.users[0]
            await client(contacts_functions.DeleteContactsRequest(id=[imported_user.id]))
            try:
                user = await client.get_entity(imported_user.id)
                if not user.phone:
                    user.phone = imported_user.phone
                return user
            except Exception:
                return imported_user
        else:
            return None
    except Exception as e:
        error(f"Error resolving phone {phone}: {e}")
        return None

async def resolve_user_from_string(client, value):
    cleaned = value.strip()
    if cleaned.startswith("+"):
        return await resolve_phone(client, cleaned)
    if cleaned.startswith("@"):
        cleaned = cleaned[1:]
    try:
        entity = await client.get_entity(int(cleaned)) if cleaned.isdigit() else await client.get_entity(cleaned)
    except UsernameNotOccupiedError:
        error(f"Username not found: {value}")
        return None
    except UsernameInvalidError:
        error(f"Invalid username: {value}")
        return None
    except PeerIdInvalidError:
        error(f"Invalid user ID: {value}")
        return None
    except ValueError:
        error(f"Could not resolve: {value}")
        return None
    except Exception as exc:
        error(f"Failed to resolve {value}: {exc}")
        return None
    if not isinstance(entity, User):
        warning(f"Resolved entity is not a user: {value} ({type(entity).__name__})")
        return None
    return entity

OUTPUT_DIR = os.getcwd()

def get_args(parser):
    """
    Module-specific CLI arguments.
    """
    parser.add_argument(
        "users",
        nargs="+",
        help="Usernames, IDs, phone numbers (starting with +), or file path containing them."
    )
    parser.add_argument(
        "--photos",
        action="store_true",
        help="Download profile photos."
    )
    parser.add_argument(
        "-o", "--out",
        nargs="?",
        const="default",
        help="Output directory (default: data/output/info). If provided, writes global JSON output."
    )
    parser.add_argument(
        "-f", "--filter",
        nargs="+",
        help="Filter output fields (e.g. id, username, first_name)."
    )

class DateTimeEncoder(json.JSONEncoder):
    """Custom JSON encoder for datetime objects."""
    def default(self, o):
        if isinstance(o, datetime):
            return o.isoformat()
        if isinstance(o, bytes):
            return "<bytes>"
        return super().default(o)

async def dump_user_info(client, user_input, args, photos_dir):
    """
    Fetches info for a single user and downloads photos if requested.
    Returns a tuple (user_id, data_dict) or None if failed.
    """
    info(f"Resolving user: {user_input}...")
    
    # 1. Resolve basic entity
    try:
        user = await resolve_user_from_string(client, user_input)
        if not user:
            error(f"Could not resolve user: {user_input}")
            return None
    except Exception as e:
        error(f"Error resolving {user_input}: {e}")
        return None

    # 2. Fetch full user details
    try:
        full_user_obj = await client(functions.users.GetFullUserRequest(id=user))
    except Exception as e:
        error(f"Failed to get full user details for {user_input}: {e}")
        return None

    # 3. Extract Data
    target_user = next((u for u in full_user_obj.users if u.id == user.id), user)
    user_full = full_user_obj.full_user

    # Prepare status string
    status_str = str(target_user.status)
    if isinstance(target_user.status, UserStatusOnline):
         status_str = f"Online (Expires: {target_user.status.expires})"
    elif isinstance(target_user.status, UserStatusOffline):
         status_str = f"Offline (Was Online: {target_user.status.was_online})"
    elif isinstance(target_user.status, UserStatusRecently):
         status_str = "Recently"
    elif isinstance(target_user.status, UserStatusLastWeek):
         status_str = "Last Week"
    elif isinstance(target_user.status, UserStatusLastMonth):
         status_str = "Last Month"

    data = {
        "id": target_user.id,
        "username": target_user.username,
        "first_name": target_user.first_name,
        "last_name": target_user.last_name,
        "phone": target_user.phone,
        "is_bot": target_user.bot,
        "is_scam": target_user.scam,
        "is_fake": getattr(target_user, 'fake', False),
        "is_premium": getattr(target_user, 'premium', False),
        "verified": target_user.verified,
        "restricted": target_user.restricted,
        "restriction_reason": getattr(target_user, 'restriction_reason', None),
        "lang_code": target_user.lang_code,
        "status": status_str,
        "about": user_full.about,
        "common_chats_count": user_full.common_chats_count,
        "pinned_msg_id": user_full.pinned_msg_id,
        "photos_downloaded": 0,
        "common_chats": []
    }

    # 3.5 Fetch Common Chats
    if user_full.common_chats_count > 0:
        try:
            # Fetch common chats
            result = await client(functions.messages.GetCommonChatsRequest(
                user_id=target_user,
                max_id=0,
                limit=DEFAULT_LIMIT
            ))
            
            common_chats_list = []
            for chat in result.chats:
                chat_info = {
                    "id": chat.id,
                    "title": chat.title,
                    "username": getattr(chat, 'username', None),
                    "type": type(chat).__name__
                }
                
                if chat_info['username']:
                    chat_info['link'] = f"https://t.me/{chat_info['username']}"
                else:
                    # For private groups/channels without username, we might not have a link readily available 
                    # unless we are admin or use export invite link, which is too intrusive.
                    chat_info['link'] = None
                    
                common_chats_list.append(chat_info)
                
            data["common_chats"] = common_chats_list
            
        except Exception as e:
            error(f"Failed to fetch common chats for {user_input}: {e}")

    # 4. Download Photos
    if args.photos:
        info(f"Downloading photos for {target_user.id}...")
        count = 0
        try:
            async for photo in client.iter_profile_photos(user):
                # Naming convention: {userid}.jpg (main), {userid}_{count}.jpg (others)
                if count == 0:
                    filename = f"{target_user.id}.jpg"
                else:
                    filename = f"{target_user.id}_{count}.jpg"
                
                path = os.path.join(photos_dir, filename)
                await client.download_media(photo, file=path)
                count += 1
            
            data["photos_downloaded"] = count
            success(f"Downloaded {count} photos for {target_user.id}")
        except Exception as e:
            error(f"Error downloading photos: {e}")

    # 5. Apply Filter
    if args.filter:
        filter_keys = set()
        for f in args.filter:
            for key in f.split(','):
                clean_key = key.strip()
                if clean_key:
                    filter_keys.add(clean_key)
        
        data = {k: v for k, v in data.items() if k in filter_keys}

    return target_user.id, data


async def run(args):
    client = await connect_client()
    
    # Determine output configuration
    write_json = args.out is not None
    if args.out and args.out != "default":
        module_output = args.out
    else:
        module_output = os.path.join(OUTPUT_DIR, "info")

    if write_json or args.photos:
        os.makedirs(module_output, exist_ok=True)
    
    # Photos directory (shared)
    photos_dir = os.path.join(module_output, "photos")
    if args.photos:
        os.makedirs(photos_dir, exist_ok=True)

    # Gather inputs
    inputs = []
    for raw_input in args.users:
        if os.path.isfile(raw_input):
            try:
                with open(raw_input, 'r', encoding='utf-8') as f:
                    for line in f:
                        processed = parse_user_inputs(line)
                        inputs.extend(processed)
            except Exception as e:
                error(f"Failed to read file {raw_input}: {e}")
        else:
            inputs.extend(parse_user_inputs(raw_input))
            
    unique_inputs = []
    seen = set()
    for item in inputs:
        if item not in seen:
            unique_inputs.append(item)
            seen.add(item)
    
    if not unique_inputs:
        error("No valid inputs parsed.")
        return

    info(f"Processing {len(unique_inputs)} users...")

    # Aggregated results
    results = {}

    for user_input in unique_inputs:
        result = await dump_user_info(client, user_input, args, photos_dir)
        if result:
            user_id, user_data = result
            results[str(user_id)] = user_data

    # Save aggregated JSON
    if results:
        if write_json:
            json_path = os.path.join(module_output, "users.json")
            try:
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(results, f, indent=4, cls=DateTimeEncoder, ensure_ascii=False)
                
                success(f"Saved data for {len(results)} users to {json_path}")
            except Exception as e:
                error(f"Failed to save main JSON file: {e}")
        
        print(json.dumps(results, indent=4, cls=DateTimeEncoder, ensure_ascii=False))
            
    else:
        warning("No user data collected.")

    await client.disconnect()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Telegram User Info Dumper")
    get_args(parser)
    args = parser.parse_args()

    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass