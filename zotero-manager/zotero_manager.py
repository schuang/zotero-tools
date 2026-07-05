#!/usr/bin/env python3
"""
zotero_manager.py - Main entry point for Zotero library maintenance tasks.

Available subcommands:
    add-url           - Add URL from DOI when URL is empty.
    clear-extra       - Clear the Extra field for items matching a prefix.
    fix-titles        - Normalise ALL-CAPS titles to sentence/title case.
    all               - Run tasks that have default arguments (dry run by default).

Each subcommand supports its own --apply flag to write changes.

Usage:
    python zotero_manager.py add-url --doi "10.1000/example" --apply
    python zotero_manager.py clear-extra --apply
    python zotero_manager.py fix-titles --apply
    python zotero_manager.py all --apply

Environment variables (or edit zotero_tasks/common.py):
    ZOTERO_USER_ID   - your numeric Zotero user ID
    ZOTERO_API_KEY   - your Zotero API key
"""

import argparse
import sys

from zotero_tasks import add_url, clear_extra, fix_titles


# ---------------------------------------------------------------------------
# Registry of all available task modules.
# ---------------------------------------------------------------------------
TASKS = {
    "add-url": add_url,
    "clear-extra": clear_extra,
    "fix-titles":  fix_titles,
}


# ---------------------------------------------------------------------------
# Main CLI dispatcher
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Zotero library maintenance - run tasks to clean and normalise your library.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    subparsers = parser.add_subparsers(dest="command", help="Task to run")

    # Register each task as a subcommand.
    for name, module in TASKS.items():
        sub = subparsers.add_parser(
            name,
            help=module.__doc__.split("\n")[0],   # first line of module docstring
        )
        module.add_arguments(sub)

    # Special "all" subcommand that runs every task sequentially.
    sub_all = subparsers.add_parser(
        "all",
        help="Run tasks that have default arguments in sequence.",
    )
    sub_all.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Write changes for all tasks. Without this flag all tasks run as dry runs.",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Dispatch
    if args.command == "all":
        run_all(args)
    else:
        module = TASKS[args.command]
        module.run(args)


def run_all(args):
    """Run all tasks in the TASKS registry, passing --apply if requested."""
    print("=" * 60)
    print("Running ALL tasks")
    print(f"Mode: {'APPLY' if args.apply else 'DRY RUN'}")
    print("=" * 60)
    print()

    # Build a minimal namespace for each task with its own --apply flag.
    # The individual task modules only need args.apply (and any task-specific
    # options, which we set to defaults here).
    for name, module in TASKS.items():
        if not getattr(module, "RUN_IN_ALL", True):
            print(f"\nSkipping task requiring explicit options: {name}")
            continue

        # Create a fresh argparse.Namespace with defaults for this task.
        # We'll inject args.apply from the global --apply flag.
        task_parser = argparse.ArgumentParser()
        module.add_arguments(task_parser)
        task_args   = task_parser.parse_args([])   # all defaults
        task_args.apply = args.apply

        print(f"\n{'=' * 60}")
        print(f"Task: {name}")
        print('=' * 60)
        try:
            module.run(task_args)
        except Exception as exc:
            print(f"✗ Task {name} failed: {exc}")
        print()


if __name__ == "__main__":
    main()
