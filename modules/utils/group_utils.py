import os
from config import GROUP_FILE

def read_groups_from_file(file_path=None):
    """
    Reads group links from a file.
    If no file_path is provided, reads from GROUP_FILE in config.
    Returns a list of non-empty stripped lines.
    """
    path = file_path or GROUP_FILE
    if not os.path.isfile(path):
        return []

    with open(path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]
