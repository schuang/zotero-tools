"""
common.py - shared utilities for all Zotero tasks.

Provides:
  - Configuration constants (USER_ID, API_KEY, …)
  - connect()          - returns an authenticated Zotero client
  - iter_items()       - pages through the full library, yielding regular items
  - format_metadata()  - human-readable summary of an item
"""

import os
import time
from pyzotero import zotero

# ---------------------------------------------------------------------------
# Configuration - read from environment variables; literals are the fallback.
# ---------------------------------------------------------------------------
USER_ID      = os.environ.get("ZOTERO_USER_ID")
API_KEY      = os.environ.get("ZOTERO_API_KEY")
LIBRARY_TYPE = "user"   # "user" or "group"
PAGE_SIZE    = 100      # Zotero API maximum per request
# ---------------------------------------------------------------------------

# Item types that are containers/metadata, not primary references.
SKIP_TYPES = {"attachment", "note"}


def connect() -> zotero.Zotero:
    """Return an authenticated pyzotero client."""
    return zotero.Zotero(USER_ID, LIBRARY_TYPE, API_KEY)


def iter_items(zot: zotero.Zotero, skip_types: set = SKIP_TYPES):
    """Yield every non-attachment, non-note item in the library.

    Handles pagination automatically and prints a progress counter.
    """
    total   = zot.count_items()
    print(f"Total items in library: {total}")
    print("Scanning items …")

    fetched = 0
    start   = 0

    while True:
        batch = zot.items(limit=PAGE_SIZE, start=start)
        if not batch:
            break

        for item in batch:
            item_type = item.get("data", {}).get("itemType", "")
            if item_type not in skip_types:
                yield item

        fetched += len(batch)
        print(f"  Scanned {fetched} / {total} items …", end="\r")

        if len(batch) < PAGE_SIZE:
            break
        start += PAGE_SIZE
        time.sleep(0.1)   # be polite to the API

    print()   # newline after the \r progress line


def format_metadata(item: dict) -> str:
    """Return a concise, human-readable summary of an item's key fields."""
    data = item.get("data", {})

    # Authors / creators
    creators     = data.get("creators", [])
    author_parts = []
    for c in creators:
        if c.get("creatorType") in ("author", "editor", "seriesEditor"):
            if "lastName" in c:
                name = c["lastName"]
                if "firstName" in c:
                    name += f", {c['firstName']}"
            else:
                name = c.get("name", "")
            author_parts.append(name)
    authors = "; ".join(author_parts) if author_parts else "(no author)"

    title     = data.get("title", "(no title)")
    date      = data.get("date", data.get("year", "(no date)"))
    venue     = (
        data.get("publicationTitle")
        or data.get("journalAbbreviation")
        or data.get("publisher")
        or data.get("bookTitle")
        or data.get("conferenceName")
        or ""
    )
    key       = data.get("key", "???")
    item_type = data.get("itemType", "")

    lines = [
        f"  Key       : {key}  [{item_type}]",
        f"  Author(s) : {authors}",
        f"  Title     : {title}",
        f"  Date      : {date}",
    ]
    if venue:
        lines.append(f"  Venue     : {venue}")
    return "\n".join(lines)
