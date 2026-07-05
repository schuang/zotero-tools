"""
add_url.py - Feature: set URL field from DOI for journal articles.

CLI usage (via zotero_manager.py):
    python zotero_manager.py add-url --doi "10.1000/example"
    python zotero_manager.py add-url --doi "10.1000/example" --apply
    python zotero_manager.py add-url --doi "10.1000/example" --url-prefix "https://doi.org"
"""

import time
from .common import connect, iter_items, format_metadata

DEFAULT_URL_PREFIX = "https://doi.org"
RUN_IN_ALL = False


def add_arguments(parser):
    """Register subcommand-specific arguments."""
    parser.add_argument(
        "--doi",
        required=True,
        help="DOI value to match before adding the URL.",
    )
    parser.add_argument(
        "--url-prefix",
        default=DEFAULT_URL_PREFIX,
        help=f"URL prefix to prepend to DOI values (default: '{DEFAULT_URL_PREFIX}').",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Write changes to Zotero. Without this flag the command is a dry run.",
    )


def make_url(url_prefix: str, doi: str) -> str:
    """Return URL_PREFIX/DOI with exactly one separator slash."""
    return f"{url_prefix.rstrip('/')}/{doi.lstrip('/')}"


def run(args):
    """Entry point called by zotero_manager.py."""
    dry_run       = not args.apply
    target_doi    = args.doi.strip()
    target_doi_lc = target_doi.lower()
    url_prefix    = args.url_prefix

    print("=" * 60)
    print("Task: Add URL from DOI")
    print(f"Mode      : {'DRY RUN' if dry_run else '*** APPLY - changes will be written ***'}")
    print(f"DOI       : {target_doi!r}")
    print(f"URL prefix: {url_prefix!r}")
    print("=" * 60)

    zot     = connect()
    matches = []   # list of (item, new_url)

    for item in iter_items(zot):
        data = item.get("data", {})
        item_type = data.get("itemType", "")
        doi       = (data.get("DOI", "") or "").strip()
        if (
            item_type == "journalArticle"
            and doi
            and doi.lower() == target_doi_lc
            and "arxiv" not in doi.lower()
        ):
            matches.append((item, make_url(url_prefix, doi)))

    print(f"\nFound {len(matches)} journal article(s) matching DOI.\n")

    if not matches:
        print("Nothing to do.")
        return

    print("-" * 60)
    for item, new_url in matches:
        print(format_metadata(item))
        print(f"  DOI       : {item['data'].get('DOI', '')}")
        print(f"  URL(was)  : {item['data'].get('url', '') or ''}")
        print(f"  URL(after): {new_url}")
        print()
    print("-" * 60)

    if dry_run:
        print(f"\n[DRY RUN] Would set URL for {len(matches)} item(s).")
        print("Re-run with --apply to make changes.")
        return

    print(f"\nSetting URL for {len(matches)} item(s) ...")
    updated = errors = 0
    for item, new_url in matches:
        key = item["data"]["key"]
        try:
            item["data"]["url"] = new_url
            zot.update_item(item)
            print(f"  Updated: {key}")
            updated += 1
            time.sleep(0.15)
        except Exception as exc:
            print(f"  Failed : {key} - {exc}")
            errors += 1

    print(f"\nDone. Updated: {updated}  Errors: {errors}")
