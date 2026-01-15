import argparse
import asyncio
import importlib
import importlib.util
import os
import sys
import shlex
import traceback
import logging
from typing import Dict, Any, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, IntPrompt
from rich.logging import RichHandler
from rich.text import Text

from modules.utils.group_utils import read_groups_from_file

# Configure logging with Rich
logging.basicConfig(
    level="INFO",
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True, markup=True)]
)

logger = logging.getLogger("TelegramTools")
console = Console()

MODULES_DIR = "modules/tasks"

class TelegramToolsApp:
    def __init__(self):
        self.modules: Dict[str, Any] = {}
        self.running = True

    def discover_modules(self) -> Dict[str, Any]:
        """Return {module_name: module_object} for all Python files in modules/tasks/ except __init__.py"""
        modules = {}
        if not os.path.isdir(MODULES_DIR):
            logger.error(f"[red]Modules directory not found: {MODULES_DIR}[/red]")
            return modules
            
        for f in os.listdir(MODULES_DIR):
            if f.endswith(".py") and f != "__init__.py":
                name = f[:-3]
                try:
                    spec = importlib.util.spec_from_file_location(
                        name, os.path.join(MODULES_DIR, f)
                    )
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        modules[name] = module
                except Exception as e:
                    logger.error(f"[red]Failed to load module {name}: {e}[/red]")
        self.modules = modules
        return modules

    async def run_module(self, module_name: str, args: argparse.Namespace):
        module = self.modules.get(module_name)
        if not module:
            logger.error(f"[red]Module '{module_name}' not found[/red]")
            return

        if hasattr(module, "run"):
            try:
                await module.run(args)
            except Exception as e:
                logger.error(f"[red]Error running module '{module_name}': {e}[/red]")
                console.print_exception()
        else:
            logger.error(f"[red]Module '{module_name}' has no run() coroutine.[/red]")

    def get_module_parser(self, module_name: str, module: Any) -> argparse.ArgumentParser:
        """
        Creates and returns an ArgumentParser for the specific module.
        """
        parser = argparse.ArgumentParser(
            prog=f"python main.py -m {module_name}",
            description=f"Arguments for {module_name} module"
        )
        
        if hasattr(module, "get_args"):
            module.get_args(parser)
        
        return parser

    def print_banner(self):
        title = Text("TelegramTools - Interactive Mode", justify="center", style="bold cyan")
        panel = Panel(
            title,
            border_style="cyan",
            padding=(1, 2)
        )
        console.print(panel)

    def process_common_args(self, args: argparse.Namespace):
        """
        Handle common post-processing logic for arguments.
        """
        if hasattr(args, "groups"):
            if not args.groups:
                # No groups provided, read from default file
                args.groups = read_groups_from_file()
            elif len(args.groups) == 1 and os.path.isfile(args.groups[0]):
                # Single argument is a file path, read groups from it
                args.groups = read_groups_from_file(args.groups[0])
            # Otherwise, args.groups is already a list of group links

    async def interactive_loop(self):
        """
        Continuously prompt user for module selection until exit.
        """
        while self.running:
            console.clear()
            self.print_banner()
            
            table = Table(title="Available Modules", show_header=True, header_style="bold magenta")
            table.add_column("ID", style="dim", width=4, justify="right")
            table.add_column("Module Name", style="green")

            module_names = sorted(list(self.modules.keys()))
            for i, name in enumerate(module_names, 1):
                table.add_row(str(i), name)

            console.print(table)
            console.print("\n[bold red]0[/bold red]) Exit")

            selected_module_name = None
            
            while not selected_module_name:
                try:
                    choice_str = Prompt.ask("\nSelect a module", default="0")
                    choice = choice_str.strip()
                    
                    if choice == '0' or choice.lower() == 'exit':
                        console.print("[yellow]Exiting...[/yellow]")
                        self.running = False
                        return

                    if choice.isdigit():
                        idx = int(choice)
                        if 1 <= idx <= len(module_names):
                            selected_module_name = module_names[idx-1]
                    elif choice in module_names:
                        selected_module_name = choice
                    
                    if not selected_module_name:
                        console.print("[red]Invalid selection. Please try again.[/red]")
                except KeyboardInterrupt:
                    console.print("\n[yellow]Exiting...[/yellow]")
                    self.running = False
                    return

            # Module selected
            console.print(f"\n[bold cyan][+] Selected Module: {selected_module_name}[/bold cyan]")
            module = self.modules[selected_module_name]
            
            # 1. Create parser and show help
            parser = self.get_module_parser(selected_module_name, module)
            console.print(Panel(f"[bold]Module Help: {selected_module_name}[/bold]", style="magenta"))
            parser.print_help()
            console.print("-" * 60, style="dim")

            # 2. Ask for arguments
            console.print("[bold]Enter arguments for the module (e.g. --limit 50).[/bold]")
            console.print("Press [bold]Enter[/bold] to run with defaults.")
            
            try:
                arg_str = Prompt.ask("Args")
            except KeyboardInterrupt:
                console.print("\n[yellow]Returning to menu.[/yellow]")
                continue

            # 3. Parse and Run
            try:
                split_args = shlex.split(arg_str)
                module_args = parser.parse_args(split_args)
                
                self.process_common_args(module_args)
                
                console.print(f"\n[bold green][+] Running {selected_module_name}...[/bold green]\n")
                await self.run_module(selected_module_name, module_args)
                
                console.print(f"\n[bold green][+] {selected_module_name} finished.[/bold green]")
                Prompt.ask("\nPress Enter to return to main menu")
                
            except SystemExit:
                # argparse calls sys.exit on error or --help
                console.print("\n[yellow][!] Argument checking failed (or help displayed). Returning to menu.[/yellow]")
                continue
            except Exception as e:
                logger.exception(f"Error during execution: {e}")
                Prompt.ask("\nPress Enter to return to main menu")

    def parse_cli_args(self):
        """
        Parse command line arguments when running in non-interactive mode.
        """
        parent_parser = argparse.ArgumentParser(add_help=False)
        parent_parser.add_argument("-m", "--module", type=str, choices=list(self.modules.keys()))
        parent_parser.add_argument("--list-modules", action="store_true")
        
        base_args, remaining_args = parent_parser.parse_known_args()

        if base_args.list_modules:
            console.print("[+] Available task modules:")
            for m in sorted(self.modules.keys()):
                console.print(f"- {m}")
            sys.exit(0)

        # Handle Help if no module selected
        if "-h" in sys.argv or "--help" in sys.argv:
            if not base_args.module:
                print("Usage: python main.py [-m MODULE] [options]")
                print("\nOptions:")
                print("  -m, --module NAME   Run a specific module")
                print("  --list-modules      List available modules")
                print("  -h, --help          Show this help message")
                print("\nIf no module is specified, Interactive Mode is entered.")
                sys.exit(0)

        return base_args.module, remaining_args

async def main():
    app = TelegramToolsApp()
    app.discover_modules()
    
    selected_module_name, remaining_args = app.parse_cli_args()

    if selected_module_name:
        # --- CLI MODE ---
        module = app.modules[selected_module_name]
        parser = app.get_module_parser(selected_module_name, module)
        
        final_args = parser.parse_args(remaining_args)
        app.process_common_args(final_args)
        
        await app.run_module(selected_module_name, final_args)
    else:
        # --- INTERACTIVE MODE ---
        await app.interactive_loop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n[!] Interrupted by user. Exiting...")
