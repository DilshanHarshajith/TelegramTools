"""
Shared utilities for user resolution and ID parsing.
"""

from typing import List, Optional, Union
from typing import List, Optional, Union
from telethon import functions
from telethon.tl.types import User, PeerUser, InputPhoneContact
from telethon.errors import UsernameInvalidError, UsernameNotOccupiedError, PeerIdInvalidError
from modules.utils.output import error, warning

def parse_user_inputs(input_str: Optional[str]) -> List[str]:
    """
    Parse a string containing multiple usernames or IDs.
    Handles mixed delimiters like commas, spaces, or both.
    Example: "@user1, user2 123456" -> ["@user1", "user2", "123456"]
    """
    if not input_str:
        return []
    
    # Replace commas with spaces to unify delimiters, then split by whitespace
    raw_parts = input_str.replace(',', ' ').split()
    
    collected = []
    seen = set()
    for part in raw_parts:
        normalized = part.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            collected.append(normalized)
    return collected


def parse_user_ids_string(input_str: Optional[str]) -> List[str]:
    """
    Parse a string of user IDs (comma or whitespace separated).
    Returns a list of unique user IDs as strings (digits only).
    """
    inputs = parse_user_inputs(input_str)
    return [i for i in inputs if i.isdigit()]


async def resolve_phone(client, phone: str) -> Optional[User]:
    """
    Resolve a phone number to a User entity.
    Attempts direct resolution first, then falls back to import-contact method.
    """
    phone = phone.strip().replace(" ", "").replace("-", "")
    
    try:
        # 1. Try to resolve directly
        try:
            entity = await client.get_entity(phone)
            if isinstance(entity, User):
                return entity
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
            
            # Now fetch the fresh entity to ensure we have the latest info
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


async def resolve_user_from_string(client, value: str) -> Optional[User]:
    """
    Resolve a username (with or without @), numeric ID string, or phone number (starting with +) to a Telethon User entity.
    """
    cleaned = value.strip()
    
    if cleaned.startswith("+"):
        return await resolve_phone(client, cleaned)

    if cleaned.startswith("@"):
        cleaned = cleaned[1:]

    try:
        # If it's digits, treat as ID, otherwise as username/link
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


async def fetch_full_user(client, user_or_id: Union[User, int, PeerUser]) -> Optional[User]:
    """
    Attempts to fetch the full User entity to ensure we have fields like username.
    Useful when the initial entity is 'min' or missing info.
    """
    try:
        if isinstance(user_or_id, int):
            user = await client.get_entity(user_or_id)
        elif isinstance(user_or_id, PeerUser):
            user = await client.get_entity(user_or_id)
        else:
            # It's already a User object, but maybe we want to refresh it
            user = await client.get_entity(user_or_id.id)
            
        if isinstance(user, User):
            return user
    except Exception:
        pass
    return None
