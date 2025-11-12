import argparse
import asyncio
import importlib
import os
import sys
from modules.utils.group_utils import read_groups_from_file

MODULES_DIR = "modules/tasks"

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
    module = modules.get(module_name)
    if not module:
        print(f"[!] Module '{module_name}' not found")
        return
    if hasattr(module, "run"):
        await module.run(args)
    else:
        print(f"[!] Module '{module_name}' has no run() coroutine.")

def parse_args(modules):
    # Step 1: parse known args to get module name
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("-m", "--module", type=str, required=True, choices=list(modules.keys()))
    parser.add_argument("--list-modules", action="store_true")
    args, unknown = parser.parse_known_args()

    if args.list_modules:
        print("[+] Available task modules:")
        for m in modules:
            print("-", m)
        sys.exit(0)

    # Step 2: full parser for module-specific args
    parser = argparse.ArgumentParser(description=f"Run module '{args.module}'")
    parser.add_argument("-m", "--module", type=str, required=True, choices=list(modules.keys()))
    module = modules.get(args.module)
    if module and hasattr(module, "get_args"):
        module.get_args(parser)

    final_args = parser.parse_args()

    # Ensure groups argument is a list
    if hasattr(final_args, "groups"):
        if final_args.groups:
            if len(final_args.groups) == 1 and os.path.isfile(final_args.groups[0]):
                final_args.groups = read_groups_from_file(final_args.groups[0])
        else:
            final_args.groups = read_groups_from_file()

    return final_args

async def main():
    modules = discover_modules()
    args = parse_args(modules)
    await run_module(args.module, modules, args)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[!] Interrupted by user. Exiting...")
