"""
Output formatting utilities for consistent console output across modules.
"""

def info(message: str) -> None:
    """Print info message with [+] prefix."""
    print(f"[+] {message}") if config.VERBOSE or config.INFO else None  

def error(message: str) -> None:
    """Print error message with [!] prefix."""
    print(f"[!] {message}") if config.VERBOSE or config.ERROR else None

def warning(message: str) -> None:
    """Print warning message with [!] prefix."""
    print(f"[!] {message}") if config.VERBOSE or config.WARNING else None

def success(message: str) -> None:
    """Print success message with [✓] prefix."""
    print(f"[✓] {message}") if config.VERBOSE or config.SUCCESS else None

def progress(message: str) -> None:
    """Print progress message with [*] prefix."""
    print(f"[*] {message}") if config.VERBOSE or config.PROGRESS else None

