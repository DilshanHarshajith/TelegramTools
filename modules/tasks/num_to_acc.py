"""
Find Telegram Account by Phone Number
-------------------------------------
"""

import os
import sys
import asyncio
import argparse
import json
from telethon import functions
from telethon.tl.types import User, InputPhoneContact

# Add project root to sys.path if running as standalone script
if __name__ == "__main__":
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

import config
from modules.utils.auth import connect_client

# ------------------------
# CLI Arguments
# ------------------------
def get_args(parser):
    parser.add_argument(
        "inputs",
        nargs="+",
        help="Phone number(s) to search (e.g., +1234567890) or file path(s) containing them."
    )
    parser.add_argument(
        "-o", "--out",
        nargs="?",
        const="default",
        help="Output JSON file path. If flag is present without path, results are saved to default directory."
    )

def get_user_dict(user: User):
    """
    Convert User object to dictionary.
    """
    data = {
        "id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "phone": user.phone,
        "is_bot": user.bot,
        "is_scam": user.scam,
        "is_fake": getattr(user, 'fake', False),
        "is_premium": getattr(user, 'premium', False),
        "verified": getattr(user, 'verified', False),
        "restriction_reason": getattr(user, 'restriction_reason', [])
    }
    if data["restriction_reason"]:
        data["restriction_reason"] = str(data["restriction_reason"])
    
    return data

async def resolve_phone(client, phone):
    """
    Resolve a single phone number to a user entity.
    Returns a dict with user data or error info.
    """
    phone = phone.strip().replace(" ", "").replace("-", "")
    
    # Basic validation
    if not phone.startswith("+"):
        if phone.isdigit():
            phone = f"+{phone}"
    
    try:
        # 1. Try to resolve directly
        try:
            entity = await client.get_entity(phone)
            if isinstance(entity, User):
                return get_user_dict(entity)
        except Exception:
            pass

        # 2. Add as contact to "force" resolution
        contact = InputPhoneContact(
            client_id=0,
            phone=phone,
            first_name="TelegramTools",
            last_name="Search"
        )
        
        result = await client(functions.contacts.ImportContactsRequest(
            contacts=[contact]
        ))

        # Check imported users
        if result.users:
            imported_user = result.users[0]
            
            # Clean up: Remove the contact we just added
            await client(functions.contacts.DeleteContactsRequest(id=[imported_user.id]))
            
            # Now fetch the fresh entity
            found_phone = imported_user.phone
            
            try:
                user = await client.get_entity(imported_user.id)
            except Exception:
                user = imported_user

            if not user.phone:
                user.phone = found_phone

            return get_user_dict(user)
        else:
            return {"error": "Not found", "phone": phone}

    except Exception as e:
        return {"error": str(e), "phone": phone}

# ------------------------
# Main entry point
# ------------------------
async def run(args):
    # Determine output mode
    output_to_file = args.out is not None

    # Silence all log output only if we are printing JSON to stdout
    if not output_to_file:
        config.VERBOSE = False
        config.INFO = False
        config.SUCCESS = False
        config.WARNING = False
        config.ERROR = False
        config.PROGRESS = False
    
    client = await connect_client()
    
    # Process inputs
    phone_numbers = []
    
    # Handle both direct strings and file paths
    for item in args.inputs:
        if os.path.isfile(item):
            try:
                with open(item, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    for line in lines:
                        clean_line = line.strip()
                        if clean_line:
                            if ',' in clean_line:
                                parts = clean_line.split(',')
                                for p in parts:
                                    p = p.strip()
                                    if p:
                                        phone_numbers.append(p)
                            else:
                                phone_numbers.append(clean_line)
            except Exception as e:
                error_msg = f"[!] Error reading file {item}: {e}"
                if output_to_file:
                    print(error_msg)
        else:
            if ',' in item:
                parts = item.split(',')
                for p in parts:
                    p = p.strip()
                    if p:
                        phone_numbers.append(p)
            else:
                phone_numbers.append(item.strip())
    
    # Deduplicate
    unique_phones = []
    seen = set()
    for p in phone_numbers:
        if p not in seen:
            unique_phones.append(p)
            seen.add(p)
    
    results = {}
    
    if output_to_file:
        print(f"[*] Processing {len(unique_phones)} phone numbers...")

    for phone_input in unique_phones:
        if output_to_file:
            print(f"[*] Searching for: {phone_input}")
        
        data = await resolve_phone(client, phone_input)
        
        # Determine key for dictionary
        # First preference: The phone number returned in the data (usually without +)
        # Second preference: The input phone number (stripped of + to match user request format)
        key_phone = data.get("phone")
        
        if not key_phone:
            # Clean input phone
            key_phone = phone_input.strip().lstrip('+')
            
        results[key_phone] = data
        
        if output_to_file:
            if "error" not in data:
                print(f"[+] Found: {data.get('first_name', 'Unknown')} ({data.get('id')})")
            else:
                print(f"[-] Not found or error: {data.get('error')}")

    await client.disconnect()

    # Output
    if output_to_file:
        # Determine path
        final_path = args.out
        if final_path == "default":
            # Default directory
            out_dir = os.path.join(config.OUTPUT_DIR, "find")
            os.makedirs(out_dir, exist_ok=True)
            final_path = os.path.join(out_dir, "results.json")
        else:
            if final_path.endswith(os.sep) or os.path.isdir(final_path):
                os.makedirs(final_path, exist_ok=True)
                final_path = os.path.join(final_path, "results.json")
            else:
                # Ensure directory exists
                parent = os.path.dirname(final_path)
                if parent:
                    os.makedirs(parent, exist_ok=True)
        
        try:
            with open(final_path, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=4, ensure_ascii=False)
            print(f"[+] Results saved to: {final_path}")
        except Exception as e:
            print(f"[!] Failed to save results: {e}")
            
    else:
        # Stdout mode
        # Always output dictionary as requested
        print(json.dumps(results, indent=4, ensure_ascii=False))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Find Telegram Account by Phone Number")
    get_args(parser)
    args = parser.parse_args()

    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass
