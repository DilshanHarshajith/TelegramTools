import os
import csv
from typing import Iterable, List, Dict, Set

from telethon.tl.types import User

from modules.utils.auth import connect_client
from modules.utils.output import info, success, warning, error
from modules.utils.user_utils import resolve_user_from_string, parse_user_inputs
from modules.utils.photo_utils import download_photos_batch, format_download_stats
from config import OUTPUT_DIR


def get_args(parser):
    """
    CLI arguments for the user_mapper module.
    """
    parser.add_argument(
        "--inputs",
        nargs="+",
        help="Usernames or user IDs to resolve (prefix @ optional for usernames)",
    )
    parser.add_argument(
        "--file",
        type=str,
        help="Path to a file containing usernames or user IDs (one per line)",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Optional CSV path for saving mappings (default: data/output/user_mapper/mappings.csv)",
    )
    parser.add_argument(
        "--photo",
        action="store_true",
        help="Optional flag to download user photos (default: False)",
    )


async def run(args):
    values = _collect_inputs(args.inputs, args.file)
    if not values:
        error("No inputs provided. Use --inputs or --file.")
        return

    client = await connect_client()
    module_output = os.path.join(OUTPUT_DIR, "user_mapper")
    os.makedirs(module_output, exist_ok=True)
    output_csv = args.output or os.path.join(module_output, "mappings.csv")

    mappings: List[Dict[str, str]] = []
    resolved_users: List[User] = []

    for raw_value in values:
        # Use shared utility to resolve user
        user = await resolve_user_from_string(client, raw_value)
        if not user:
            continue
        
        resolved_users.append(user)

        mapping = {
            "input": raw_value,
            "user_id": str(user.id),
            "username": (user.username or "").lstrip("@"),
            "first_name": user.first_name or "",
            "last_name": user.last_name or "",
        }
        mappings.append(mapping)

        username_display = f"@{mapping['username'] if mapping['username'] else '<no_username>'}  | {mapping['first_name']} {mapping['last_name']}"
        success(f"{raw_value} -> id: {mapping['user_id']} | username: {username_display}")

    _write_mappings_csv(output_csv, mappings)
    
    if args.photo and resolved_users:
        info("Downloading profile photos...")
        stats = await download_photos_batch(client, resolved_users, module_output, verbose=True)
        success(format_download_stats(*stats))

    await client.disconnect()
    success(f"Saved {len(mappings)} mapping(s) to {output_csv}")


def _collect_inputs(cli_values: Iterable[str], file_path: str) -> List[str]:
    """
    Combine CLI inputs and file-based inputs, preserving order and removing duplicates.
    """
    collected: List[str] = []
    seen: Set[str] = set()

    def _add_many(values: Iterable[str]):
        for val in values:
            parsed = parse_user_inputs(val)
            for item in parsed:
                if item not in seen:
                    seen.add(item)
                    collected.append(item)

    if cli_values:
        _add_many(cli_values)

    if file_path:
        if not os.path.isfile(file_path):
            error(f"File not found: {file_path}")
        else:
            with open(file_path, "r", encoding="utf-8") as f:
                _add_many(f)

    return collected


def _write_mappings_csv(csv_path: str, rows: List[Dict[str, str]]) -> None:
    """
    Append mappings to a CSV file, adding a header if the file does not yet exist.
    Prevents duplicate records based on user_id.
    """
    file_exists = os.path.isfile(csv_path)
    os.makedirs(os.path.dirname(csv_path) or ".", exist_ok=True)

    # Read existing user IDs to avoid duplicates
    existing_user_ids: Set[str] = set()
    if file_exists:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if reader and reader.fieldnames:
                for row in reader:
                    if row.get("user_id"):
                        existing_user_ids.add(row["user_id"])

    # Write new records, skipping duplicates
    with open(csv_path, "a", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        if not file_exists:
            writer.writerow(["input", "user_id", "username", "first_name", "last_name"])

        for row in rows:
            user_id = row.get("user_id", "")
            if user_id and user_id not in existing_user_ids:
                writer.writerow([
                    row.get("input", ""),
                    user_id,
                    row.get("username", ""),
                    row.get("first_name", ""),
                    row.get("last_name", ""),
                ])
                existing_user_ids.add(user_id)

