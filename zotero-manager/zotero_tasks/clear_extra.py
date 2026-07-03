"""
clear_extra.py - Feature: clear the "Extra" field for items where it starts
with a known prefix (default: "LLMKB SHA256").

CLI usage (via zotero_manager.py):
    python zotero_manager.py clear-extra
    python zotero_manager.py clear-extra --apply
    python zotero_manager.py clear-extra --prefix "MY PREFIX"
"""

import time
from .common import connect, iter_items, format_metadata

DEFAULT_PREFIX = "LLMKB SHA256"


def add_arguments(parser):
    """Register subcommand-specific arguments."""
    parser.add_argument(
        "--prefix",
        default=DEFAULT_PREFIX,
        help=f"Trigger prefix to match in the Extra field (default: '{DEFAULT_PREFIX}').",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Write changes to Zotero. Without this flag the command is a dry run.",
    )


def run(args):
    """Entry point called by zotero_manager.py."""
    dry_run = not args.apply
    prefix  = args.prefix

    print("=" * 60)
    print("Task: Clear Extra field")
    print(f"Mode  : {'DRY RUN' if dry_run else '*** APPLY - changes will be written ***'}")
    print(f"Prefix: {prefix!r}")
    print("=" * 60)

    zot     = connect()
    matches = []

    for item in iter_items(zot):
        extra = item.get("data", {}).get("extra", "") or ""
        if extra.startswith(prefix):
            matches.append(item)

    print(f"\nFound {len(matches)} item(s) whose Extra field starts with {prefix!r}.\n")

    if not matches:
        print("Nothing to do.")
        return

    print("-" * 60)
    for item in matches:
        print(format_metadata(item))
        extra_snippet = (item["data"].get("extra", "") or "")[:120]
        print(f"  Extra(was): {extra_snippet!r}")
        print()
    print("-" * 60)

    if dry_run:
        print(f"\n[DRY RUN] Would clear Extra for {len(matches)} item(s).")
        print("Re-run with --apply to make changes.")
        return

    print(f"\nClearing Extra field for {len(matches)} item(s) …")
    cleared = errors = 0
    for item in matches:
        key = item["data"]["key"]
        try:
            item["data"]["extra"] = ""
            zot.update_item(item)
            print(f"  ✓ Cleared: {key}")
            cleared += 1
            time.sleep(0.15)
        except Exception as exc:
            print(f"  ✗ Failed : {key} - {exc}")
            errors += 1

    print(f"\nDone. Cleared: {cleared}  Errors: {errors}")
