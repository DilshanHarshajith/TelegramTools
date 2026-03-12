import os
import sys
import asyncio
import tty
import termios
import select
from typing import List, Optional

IS_INTERACTIVE = True

from telethon import TelegramClient, events
from telethon.tl.types import User, Chat, Channel, ChatBannedRights
from telethon.tl.functions.messages import GetHistoryRequest
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, IntPrompt
from rich.layout import Layout
from rich.live import Live
from rich.text import Text
from rich.align import Align

# ---------------------------------------------------------------------------
# Path setup — makes config.py importable from anywhere
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

try:
    import config as _cfg
except ImportError:
    import getpass
    from pathlib import Path

    def _load_dotenv(path):
        vals = {}
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, val = line.partition("=")
                    vals[key.strip()] = val.strip().strip('"').strip("'")
        except OSError:
            pass
        return vals

    class _cfg:
        _api_id = _api_hash = None
        _session = "session"
        VERBOSE = True; INFO = True; SUCCESS = True; PROGRESS = True
        WARNING = False; ERROR = False
        GROUP_FILE = "groups.txt"
        DEFAULT_LIMIT = 1000
        REPLY_ITER_LIMIT = 500

        _here = Path(__file__).resolve().parent
        for _p in dict.fromkeys([_here / ".env", Path.home() / ".env", Path.cwd() / ".env"]):
            if _p.is_file():
                _d = _load_dotenv(_p)
                _api_id   = _d.get("API_ID")   or _api_id
                _api_hash = _d.get("API_HASH")  or _api_hash
                _session  = _d.get("SESSION_NAME", _session)
                if _api_id and _api_hash:
                    print(f"[*] Credentials loaded from {_p}")
                    break

        if not (_api_id and _api_hash):
            _api_id   = os.getenv("API_ID")   or _api_id
            _api_hash = os.getenv("API_HASH") or _api_hash

        if not (_api_id and _api_hash):
            print("\n[!] Telegram API credentials not found.")
            print("    Get yours at https://my.telegram.org/apps\n")
            while not _api_id:
                _raw = input("    API_ID  (numeric): ").strip()
                if _raw.isdigit():
                    _api_id = _raw
                else:
                    print("    API_ID must be a number — please try again.")
            while not _api_hash:
                _raw = getpass.getpass("    API_HASH (hidden): ").strip()
                if _raw:
                    _api_hash = _raw
                else:
                    print("    API_HASH cannot be empty — please try again.")
            if input("\n    Save to .env in current directory? [y/N] ").strip().lower() == "y":
                _env_path = Path.cwd() / ".env"
                with open(_env_path, "a", encoding="utf-8") as _f:
                    _f.write(f"\nAPI_ID={_api_id}\nAPI_HASH={_api_hash}\n")
                print(f"    Saved to {_env_path}\n")

        API_ID       = int(_api_id)
        API_HASH     = str(_api_hash)
        SESSION_NAME = _session

API_ID       = _cfg.API_ID
API_HASH     = _cfg.API_HASH
SESSION_NAME = _cfg.SESSION_NAME
def get_client():
    return TelegramClient(SESSION_NAME, API_ID, API_HASH)

async def connect_client():
    client = get_client()
    await client.start()
    return client

OUTPUT_DIR = os.getcwd()

console = Console()

def get_args(parser):
    """Module-specific arguments."""
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Number of chats to display in the list"
    )

async def get_chat_list(client: TelegramClient, limit: int):
    """Fetch the list of latest dialogs."""
    dialogs = await client.get_dialogs(limit=limit)
    return dialogs

def format_chat_list(dialogs):
    """Create a Rich table for the chat list."""
    table = Table(title="Recent Chats", show_header=True, header_style="bold magenta")
    table.add_column("ID", style="dim", width=4, justify="right")
    table.add_column("Name", style="green")
    table.add_column("Last Message", style="white", overflow="ellipsis")
    table.add_column("Unread", style="yellow", justify="center")

    for i, dialog in enumerate(dialogs, 1):
        name = dialog.name or "Unknown"
        last_msg = dialog.message.message if dialog.message and dialog.message.message else "<Media/Encrypted>"
        last_msg = last_msg.replace("\n", " ")[:50]
        unread = str(dialog.unread_count) if dialog.unread_count > 0 else "-"
        table.add_row(str(i), name, last_msg, unread)
    
    return table

async def display_messages(client, chat, limit=20):
    """Fetch and format message history."""
    try:
        messages = await client.get_messages(chat, limit=limit)
        messages = list(messages)
    except Exception as e:
        return [Panel(f"[red]Could not load messages: {e}[/red]", border_style="red")]
        
    messages.reverse()  # Oldest first

    history_panel = []
    for msg in messages:
        sender_name = "System"
        if msg.sender:
            if isinstance(msg.sender, User):
                sender_name = f"{msg.sender.first_name or ''} {msg.sender.last_name or ''}".strip() or msg.sender.username or "User"
            else:
                sender_name = getattr(msg.sender, 'title', 'Chat')

        msg_text = msg.message or "<Media>"
        time_str = msg.date.strftime("%H:%M")
        
        if msg.out:
            # Outgoing message
            history_panel.append(Align.right(Panel(f"[bold cyan]You[/bold cyan] [dim]{time_str}[/dim]\n{msg_text}", border_style="cyan", width=60)))
        else:
            # Incoming message
            history_panel.append(Align.left(Panel(f"[bold green]{sender_name}[/bold green] [dim]{time_str}[/dim]\n{msg_text}", border_style="green", width=60)))
    
    return history_panel

async def can_send_messages(client, entity):
    """Check if the user has permission to send messages in the chat."""
    if isinstance(entity, User):
        return True
    
    try:
        permissions = await client.get_permissions(entity)
        return permissions.send_messages
    except Exception:
        # Fallback for some group types or if get_permissions fails
        if hasattr(entity, 'default_banned_rights') and entity.default_banned_rights:
            return not entity.default_banned_rights.send_messages
        return True

def get_input_with_esc(prompt_text):
    """
    Experimental raw input reader to detect Esc key.
    If Esc is pressed, returns None. Otherwise returns the string.
    """
    sys.stdout.write(prompt_text)
    sys.stdout.flush()
    
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    input_str = ""
    
    try:
        tty.setraw(sys.stdin.fileno())
        while True:
            if select.select([sys.stdin], [], [], 0.05)[0]:
                char = sys.stdin.read(1)
                if char == '\x1b':  # Esc key
                    return None
                elif char == '\r' or char == '\n':  # Enter key
                    sys.stdout.write('\r\n')
                    return input_str
                elif char == '\x7f':  # Backspace
                    if len(input_str) > 0:
                        input_str = input_str[:-1]
                        sys.stdout.write('\b \b')
                        sys.stdout.flush()
                elif char == '\x03':  # Ctrl+C
                    raise KeyboardInterrupt
                else:
                    input_str += char
                    sys.stdout.write(char)
                    sys.stdout.flush()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

async def chat_interaction(client, chat):
    """Handles the interactive loop for a specific chat."""
    chat_title = getattr(chat, 'name', getattr(chat, 'title', 'Unknown'))
    
    # Permission check
    can_post = await can_send_messages(client, chat)

    while True:
        os.system('clear' if os.name == 'posix' else 'cls')
        
        # Header
        perm_text = "" if can_post else " [red](Read Only)[/red]"
        console.print(Panel(
            Align.center(f"[bold white]Chatting with: {chat_title}[/bold white]{perm_text}"),
            style="bold blue", 
            border_style="bright_blue",
            subtitle="[dim]Type /back to exit, /refresh to update. Press Esc to exit.[/dim]"
        ))
        
        messages_rendered = await display_messages(client, chat)
        for p in messages_rendered:
            console.print(p)
        
        console.print("\n" + "─" * console.width, style="dim")
        
        if not can_post:
            console.print("[yellow]You do not have permission to post messages in this chat.[/yellow]")
            user_input = Prompt.ask("[dim]Press Enter to refresh or type /back to exit[/dim]", default="")
        else:
            try:
                # Custom input with Esc support
                user_input = get_input_with_esc(f"You: ")
                if user_input is None:  # Esc pressed
                    break
            except KeyboardInterrupt:
                break
        
        if user_input.lower() == '/back':
            break
        elif user_input.lower() == '/refresh' or user_input == "":
            continue
        elif user_input.strip() and can_post:
            try:
                await client.send_message(chat, user_input)
                await asyncio.sleep(0.3)
            except Exception as e:
                console.print(f"[red]Error sending message: {e}[/red]")
                await asyncio.sleep(1)

async def search_chat(client):
    """Search for a contact/chat by username, phone, or ID."""
    console.print("\n[bold yellow]Search for a chat[/bold yellow]")
    query = Prompt.ask("Enter username, phone number, or Chat ID")
    
    try:
        # Convert to int if it's an ID
        if query.isdigit() or (query.startswith('-') and query[1:].isdigit()):
            identifier = int(query)
        else:
            identifier = query
            
        entity = await client.get_entity(identifier)
        return entity
    except ValueError:
        console.print("[red]Could not find any chat with that identifier.[/red]")
    except Exception as e:
        console.print(f"[red]Error finding chat: {e}[/red]")
    
    await asyncio.sleep(1.5)
    return None

async def run(args):
    client = await connect_client()
    
    try:
        while True:
            os.system('clear' if os.name == 'posix' else 'cls')
            console.print(Panel("[bold cyan]Terminal Chat - Select a Chat[/bold cyan]", border_style="cyan"))
            
            dialogs = await get_chat_list(client, args.limit)
            table = format_chat_list(dialogs)
            console.print(table)
            console.print("\n[bold yellow]s[/bold yellow]) Search for a contact/group")
            console.print("[bold red]0[/bold red]) Back to Main Menu")
            
            choice = Prompt.ask("\nSelect chat ID or 's' to search", default="0")
            
            if choice == '0':
                break
            
            if choice.lower() == 's':
                selected_chat = await search_chat(client)
                if selected_chat:
                    await chat_interaction(client, selected_chat)
                continue

            if choice.isdigit():
                idx = int(choice)
                if 1 <= idx <= len(dialogs):
                    selected_chat = dialogs[idx-1]
                    await chat_interaction(client, selected_chat)
                else:
                    console.print("[red]Invalid selection![/red]")
                    await asyncio.sleep(1)
            else:
                console.print("[red]Invalid input![/red]")
                await asyncio.sleep(1)

    finally:
        if __name__ == "__main__":
            await client.disconnect()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Terminal Chat")
    get_args(parser)
    args = parser.parse_args()
    try:
        asyncio.run(run(args))
    except (KeyboardInterrupt, SystemExit):
        pass