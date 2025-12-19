"""
Shared utilities for user resolution and ID parsing.
"""

from typing import List, Optional, Union
from telethon.tl.types import User, PeerUser
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
