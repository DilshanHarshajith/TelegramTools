"""
Shared utilities for user resolution and ID parsing.
"""

from typing import List, Optional, Union
from telethon.tl.types import User, PeerUser
from telethon.errors import UsernameInvalidError, UsernameNotOccupiedError, PeerIdInvalidError
from modules.utils.output import error, warning

def parse_user_ids_string(input_str: Optional[str]) -> List[str]:
    """
    Parse a string of user IDs (comma or whitespace separated).
    Returns a list of unique user IDs as strings.
    """
    if not input_str:
        return []

    raw_parts = []
    if ',' in input_str:
        raw_parts = input_str.split(',')
    else:
        raw_parts = input_str.split()

    # Filter digits and strip whitespace
    user_ids = [part.strip() for part in raw_parts if part.strip().isdigit()]

    # Deduplicate while preserving order
    seen = set()
    unique_ids = []
    for uid in user_ids:
        if uid not in seen:
            seen.add(uid)
            unique_ids.append(uid)
            
    return unique_ids


async def resolve_user_from_string(client, value: str) -> Optional[User]:
    """
    Resolve a username (with or without @) or numeric ID string to a Telethon User entity.
    """
    cleaned = value.strip()
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
