"""
Utilities for downloading Telegram profile photos.
"""

import os
import asyncio
from telethon.tl.types import User
from telethon.errors import FloodWaitError
from modules.utils.output import error, warning, success, progress

async def download_user_photo(client, user: User, output_dir: str, user_id: str = None, verbose: bool = False) -> tuple[bool, str]:
    """
    Download profile photo for a user.
    
    Args:
        client: Telegram client instance
        user: User entity
        output_dir: Directory to save photo
        user_id: Optional user ID for filename (defaults to user.id)
        verbose: Whether to print verbose messages
        
    Returns:
        Tuple of (success: bool, status: str) where status is:
        - "success": Photo downloaded successfully
        - "skipped_exists": File already exists
        - "no_photo": User has no profile photo
        - "failed": Download failed
        - "not_user": Entity is not a User type
    """
    if not isinstance(user, User):
        if verbose:
            error(f"Skipping non-User entity: {type(user).__name__}")
        return False, "not_user"
    
    if not user.photo:
        if verbose:
            progress(f"User {user.id} has no profile photo")
        return False, "no_photo"
    
    user_id = user_id or str(user.id)
    filename = os.path.join(output_dir, f"{user_id}.jpg")
    
    # Skip if file already exists
    if os.path.isfile(filename):
        if verbose:
            progress(f"Skipping {user_id}: file already exists")
        return False, "skipped_exists"
    
    try:
        await client.download_profile_photo(user, file=filename)
        if verbose:
            username = getattr(user, 'username', None) or user_id
            success(f"Downloaded: {username}")
        return True, "success"
    except FloodWaitError as e:
        warning(f"Flood wait {e.seconds}s. Waiting...")
        await asyncio.sleep(e.seconds)
        # Retry after flood wait
        try:
            await client.download_profile_photo(user, file=filename)
            if verbose:
                username = getattr(user, 'username', None) or user_id
                success(f"Downloaded: {username}")
            return True, "success"
        except Exception as retry_e:
            if verbose:
                error(f"Failed to download photo for {user_id} after retry: {retry_e}")
            return False, "failed"
    except Exception as e:
        if verbose:
            error(f"Failed to download photo for {user_id}: {e}")
        return False, "failed"

async def download_photos_batch(client, users: list, output_dir: str, verbose: bool = False) -> tuple[int, int, int, int]:
    """
    Download photos for a batch of users.
    
    Args:
        client: Telegram client instance
        users: List of User entities
        output_dir: Directory to save photos
        verbose: Whether to print verbose messages
        
    Returns:
        Tuple of (successful_count, skipped_count, no_photo_count, failed_count)
    """
    successful = 0
    skipped = 0
    no_photo = 0
    failed = 0
    
    for user in users:
        success_flag, status = await download_user_photo(client, user, output_dir, verbose=verbose)
        if success_flag:
            successful += 1
        elif status == "skipped_exists":
            skipped += 1
        elif status == "no_photo":
            no_photo += 1
        else:
            failed += 1
    
    return successful, skipped, no_photo, failed

