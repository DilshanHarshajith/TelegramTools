"""
Output formatting utilities for consistent console output across modules.
"""

def info(message: str) -> None:
    """Print info message with [+] prefix."""
    print(f"[+] {message}")

def error(message: str) -> None:
    """Print error message with [!] prefix."""
    print(f"[!] {message}")

def warning(message: str) -> None:
    """Print warning message with [!] prefix."""
    print(f"[!] {message}")

def success(message: str) -> None:
    """Print success message with [✓] prefix."""
    print(f"[✓] {message}")

def progress(message: str) -> None:
    """Print progress message with [*] prefix."""
    print(f"[*] {message}")

