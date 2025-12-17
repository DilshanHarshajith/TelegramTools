"""
Utilities for CSV file operations.
"""

import os
import csv
from typing import List, Set

def read_existing_user_ids(csv_path: str) -> Set[str]:
    """
    Read existing user IDs from a CSV file.
    
    Args:
        csv_path: Path to CSV file
        
    Returns:
        Set of user IDs as strings
    """
    existing_uids = set()
    
    if not os.path.isfile(csv_path):
        return existing_uids
    
    try:
        with open(csv_path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if "user_id" in row:
                    existing_uids.add(row["user_id"])
    except (csv.Error, KeyError, OSError) as e:
        from modules.utils.output import warning
        warning(f"Could not read existing CSV file: {e}")
        warning("Starting with empty user list")
    
    return existing_uids

def write_user_to_csv(csv_path: str, user_id: str, username: str, first_name: str, last_name: str, file_exists: bool = False) -> None:
    """
    Write a user entry to CSV file.
    
    Args:
        csv_path: Path to CSV file
        user_id: User ID
        username: Username
        first_name: First name
        last_name: Last name
        file_exists: Whether the file already exists (to determine if header should be written)
    """
    with open(csv_path, "a", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        if not file_exists:
            writer.writerow(["user_id", "username", "first_name", "last_name"])
        writer.writerow([
            str(user_id),
            username or "",
            first_name or "",
            last_name or "",
        ])

def parse_user_ids_from_csv(csv_path: str) -> List[str]:
    """
    Parse user IDs from a CSV file.
    Supports two formats:
    1. CSV with headers (user_id column or first column)
    2. Simple text file with user IDs separated by commas or newlines
    
    Args:
        csv_path: Path to CSV file
        
    Returns:
        List of user IDs as strings
    """
    user_ids = []
    
    if not os.path.isfile(csv_path):
        from modules.utils.output import error
        error(f"CSV file not found: {csv_path}")
        return user_ids
    
    try:
        with open(csv_path, "r", newline="", encoding="utf-8") as f:
            # Try to read as CSV first
            try:
                # Read first line to check format
                first_line = f.readline().strip()
                f.seek(0)
                
                # Check if first line looks like a header (contains "user_id" or is not all digits)
                if "user_id" in first_line.lower() or not first_line.split(',')[0].strip().isdigit():
                    # Has header, use DictReader
                    reader = csv.DictReader(f)
                    for row in reader:
                        # Try to find user_id column (case insensitive)
                        uid = None
                        for key in row.keys():
                            if "user_id" in key.lower():
                                uid = row[key].strip()
                                break
                        
                        # If no user_id column found, try first column
                        if not uid and row:
                            first_value = list(row.values())[0].strip() if row.values() else ""
                            if first_value and first_value.isdigit():
                                uid = first_value
                        
                        if uid and uid.isdigit():
                            user_ids.append(uid)
                else:
                    # No header, use regular reader
                    reader = csv.reader(f)
                    for row in reader:
                        if row and row[0].strip().isdigit():
                            user_ids.append(row[0].strip())
            except (csv.Error, IndexError):
                # Not a proper CSV, try reading as simple text file
                f.seek(0)
                content = f.read()
                # Try comma-separated first
                if ',' in content:
                    user_ids = [uid.strip() for uid in content.split(',') if uid.strip() and uid.strip().isdigit()]
                else:
                    # Newline-separated
                    user_ids = [uid.strip() for uid in content.split('\n') if uid.strip() and uid.strip().isdigit()]
    except Exception as e:
        from modules.utils.output import error
        error(f"Error reading CSV file: {e}")
        return []
    
    # Remove duplicates while preserving order
    seen = set()
    unique_ids = []
    for uid in user_ids:
        if uid not in seen:
            seen.add(uid)
            unique_ids.append(uid)
    
    return unique_ids

