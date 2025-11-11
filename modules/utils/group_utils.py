import os

DEFAULT_GROUPS_FILE = "groups.txt"

def read_groups_from_file(file_path=None):
    """
    Reads group links from a file.
    If no file_path is provided, reads from DEFAULT_GROUPS_FILE.
    Returns a list of non-empty stripped lines.
    """
    path = file_path or DEFAULT_GROUPS_FILE
    if not os.path.isfile(path):
        return []

    with open(path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]
