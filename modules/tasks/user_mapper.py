import os
import csv
from typing import Iterable, List, Dict, Set

from telethon.errors import UsernameInvalidError, UsernameNotOccupiedError, PeerIdInvalidError
from telethon.tl.types import User

from modules.utils.auth import connect_client
from modules.utils.output import info, success, warning, error
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

    for raw_value in values:
        user = await _resolve_user(client, raw_value)
        if not user:
            continue

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

    await client.disconnect()

    if not mappings:
        warning("No valid mappings were created.")
        return

    _write_mappings_csv(output_csv, mappings)
    success(f"Saved {len(mappings)} mapping(s) to {output_csv}")


def _collect_inputs(cli_values: Iterable[str], file_path: str) -> List[str]:
    """
    Combine CLI inputs and file-based inputs, preserving order and removing duplicates.
    """
    collected: List[str] = []
    seen: Set[str] = set()

    def _add(value: str):
        normalized = value.strip()
        if not normalized:
            return
        if normalized in seen:
            return
        seen.add(normalized)
        collected.append(normalized)

    if cli_values:
        for val in cli_values:
            _add(val)

    if file_path:
        if not os.path.isfile(file_path):
            error(f"File not found: {file_path}")
        else:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    _add(line)

    return collected


async def _resolve_user(client, value: str):
    """
    Resolve a username or user ID to a Telethon User entity.
    """
    cleaned = value.strip()
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
    except Exception as exc:  # Fallback for unexpected errors
        error(f"Failed to resolve {value}: {exc}")
        return None

    if not isinstance(entity, User):
        warning(f"Resolved entity is not a user: {value} ({type(entity).__name__})")
        return None

    return entity


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

