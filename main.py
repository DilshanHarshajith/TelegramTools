import argparse
import asyncio
import importlib
import os
import sys

# --- Directory for task modules ---
MODULES_DIR = "modules/tasks"

# --- Helper for reading groups ---
from modules.utils.group_utils import read_groups_from_file


def discover_modules():
    """Return {module_name: module_object} for all Python files in modules/tasks/ except __init__.py"""
    modules = {}
    for f in os.listdir(MODULES_DIR):
        if f.endswith(".py") and f != "__init__.py":
            name = f[:-3]
            spec = importlib.util.spec_from_file_location(
                name, os.path.join(MODULES_DIR, f)
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            modules[name] = module
    return modules


async def run_module(module_name, modules, args):
    """Run a specific task module"""
    module = modules.get(module_name)
    if not module:
        print(f"[!] Module '{module_name}' not found")
        return

    if hasattr(module, "run"):
        await module.run(args)
    elif hasattr(module, "main"):
        await module.main(args)
    else:
        print(f"[!] Module '{module_name}' does not have run() or main() coroutine.")


def parse_args(modules):
    """Parse CLI arguments, including module-specific args"""
    parser = argparse.ArgumentParser(
        description="Telegram Modular Toolkit — dynamic modules with custom arguments"
    )
    parser.add_argument(
        "-m", "--module",
        type=str,
        required=True,
        choices=list(modules.keys()),
        help="Task module to run"
    )
    parser.add_argument(
        "-g", "--groups",
        nargs="*",
        help="Groups to process (overrides groups.txt). Can be group links or a file containing links, one per line."
    )
    parser.add_argument(
        "--list-modules",
        action="store_true",
        help="List all available task modules"
    )

    # Parse known args first to determine module
    args, unknown = parser.parse_known_args()
    module_name = args.module

    # Let module add custom args if it has get_args()
    module = modules.get(module_name)
    if module and hasattr(module, "get_args"):
        parser = argparse.ArgumentParser(
            description=f"Arguments for module '{module_name}'"
        )
        parser.add_argument(
            "-m", "--module",
            type=str,
            required=True,
            choices=list(modules.keys()),
            help="Task module to run"
        )
        parser.add_argument("-g", "--groups", nargs="*", help="Groups to process")
        module.get_args(parser)

    # Final parse
    args = parser.parse_args()

    # --- Handle groups argument ---
    if args.groups:
        # If a single argument is a file, read groups from it
        if len(args.groups) == 1 and os.path.isfile(args.groups[0]):
            args.groups = read_groups_from_file(args.groups[0])
    else:
        # Fallback to default groups.txt
        args.groups = read_groups_from_file()

    return args


async def main():
    modules = discover_modules()

    # Handle --list-modules
    if "--list-modules" in sys.argv:
        print("[+] Available task modules:")
        for m in modules:
            print("-", m)
        return

    args = parse_args(modules)
    await run_module(args.module, modules, args)


if __name__ == "__main__":
    asyncio.run(main())
