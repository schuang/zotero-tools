"""
fix_titles.py - Feature: normalise ALL-CAPS titles to sentence or title case.

Rules:
  - Only titles where every alphabetic character is upper-case are touched.
  - Sentence case → journalArticle, magazineArticle, newspaperArticle,
                     preprint, conferencePaper, report, (all other types)
  - Title case    → book, bookSection, thesis, encyclopediaArticle,
                     dictionaryEntry
  - Acronym rule  → any word that is ≤4 alphabetic characters and was
                     all-caps in the original is preserved (DNA, HIV, NLP …).
  - Sub-title rule → the first word after ":" or "—" / "-" is always
                     capitalised.

CLI usage (via zotero_manager.py):
    python zotero_manager.py fix-titles
    python zotero_manager.py fix-titles --apply
"""

import re
import time
from .common import connect, iter_items, format_metadata

# Item types that get Title Case; everything else gets Sentence case.
TITLE_CASE_TYPES = {
    "book", "bookSection", "thesis",
    "encyclopediaArticle", "dictionaryEntry",
}

# Words that stay lower-case in title case unless first, last, or after a boundary.
_MINOR = {
    # articles
    "a", "an", "the",
    # coordinating conjunctions
    "and", "but", "or", "nor", "for", "so", "yet",
    # short prepositions
    "as", "at", "by", "in", "of", "on", "to", "up", "via", "vs", "vs.",
    # longer prepositions (still treated as minor per Chicago/APA)
    "about", "above", "across", "after", "against", "along", "among",
    "around", "before", "behind", "below", "beneath", "beside", "between",
    "beyond", "during", "except", "inside", "into", "near", "onto",
    "outside", "over", "past", "since", "through", "throughout", "toward",
    "towards", "under", "until", "upon", "within", "without",
}

# Boundary punctuation that triggers capitalisation of the next word.
_BOUNDARIES = (":", "—", "-")


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def is_all_caps_title(title: str) -> bool:
    """True if every alphabetic character in *title* is upper-case."""
    letters = [c for c in title if c.isalpha()]
    return bool(letters) and all(c.isupper() for c in letters)


def _is_acronym(word: str) -> bool:
    """True if *word* should be preserved as an acronym.

    Criteria: purely alphabetic, ≤ 4 characters, and already all-caps
    (caller should pass the original casing from the ALL-CAPS source).
    """
    return word.isalpha() and len(word) <= 4 and word.isupper()


def _apply_case(word: str, capitalise: bool) -> str:
    """Return *word* with the requested casing, preserving acronyms.

    *word* is the token from the ALL-CAPS original.
    *capitalise* = True  → First-letter-up, rest lower.
    *capitalise* = False → all lower-case.
    Acronyms bypass both rules.
    """
    if _is_acronym(word):
        return word

    # Isolate leading/trailing non-alpha punctuation so we only touch the core.
    m = re.fullmatch(r"([^a-zA-Z]*)([a-zA-Z][a-zA-Z\-''\u2019]*)([^a-zA-Z]*)", word)
    if not m:
        return word.lower()

    prefix, core, suffix = m.group(1), m.group(2), m.group(3)
    if capitalise:
        return prefix + core[0].upper() + core[1:].lower() + suffix
    return prefix + core.lower() + suffix


def _ends_with_boundary(token: str) -> bool:
    return token.rstrip().endswith(_BOUNDARIES)


# ---------------------------------------------------------------------------
# Conversion functions
# ---------------------------------------------------------------------------

def to_sentence_case(title: str) -> str:
    tokens          = title.split()
    result          = []
    capitalise_next = True   # always capitalise the first word

    for tok in tokens:
        result.append(_apply_case(tok, capitalise=capitalise_next))
        capitalise_next = _ends_with_boundary(tok)

    return " ".join(result)


def to_title_case(title: str) -> str:
    tokens = title.split()
    n      = len(tokens)
    result = []

    for i, tok in enumerate(tokens):
        is_first        = (i == 0)
        is_last         = (i == n - 1)
        after_boundary  = i > 0 and _ends_with_boundary(tokens[i - 1])
        force_cap       = is_first or is_last or after_boundary

        core_lower = re.sub(r"[^a-zA-Z]", "", tok).lower()
        is_minor   = (core_lower in _MINOR) and not force_cap

        result.append(_apply_case(tok, capitalise=not is_minor))

    return " ".join(result)


def normalise_title(title: str, item_type: str) -> str | None:
    """Return the corrected title string, or None if no change is needed."""
    if not is_all_caps_title(title):
        return None

    new_title = (
        to_title_case(title)
        if item_type in TITLE_CASE_TYPES
        else to_sentence_case(title)
    )
    return new_title if new_title != title else None


# ---------------------------------------------------------------------------
# Subcommand interface
# ---------------------------------------------------------------------------

def add_arguments(parser):
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Write changes to Zotero. Without this flag the command is a dry run.",
    )


def run(args):
    dry_run = not args.apply

    print("=" * 60)
    print("Task: Fix ALL-CAPS titles")
    print(f"Mode : {'DRY RUN' if dry_run else '*** APPLY - changes will be written ***'}")
    print("=" * 60)

    zot     = connect()
    matches = []   # list of (item, new_title)

    for item in iter_items(zot):
        data      = item.get("data", {})
        title     = data.get("title", "") or ""
        item_type = data.get("itemType", "")
        new_title = normalise_title(title, item_type)
        if new_title:
            matches.append((item, new_title))

    print(f"\nFound {len(matches)} item(s) with ALL-CAPS titles.\n")

    if not matches:
        print("Nothing to do.")
        return

    print("-" * 60)
    for item, new_title in matches:
        itype     = item["data"].get("itemType", "")
        style     = "title case" if itype in TITLE_CASE_TYPES else "sentence case"
        old_title = item["data"].get("title", "")
        key       = item["data"]["key"]
        print(f"  Key   : {key}  [{itype}] → {style}")
        print(f"  Before: {old_title}")
        print(f"  After : {new_title}")
        print()
    print("-" * 60)

    if dry_run:
        print(f"\n[DRY RUN] Would update titles for {len(matches)} item(s).")
        print("Re-run with --apply to make changes.")
        return

    print(f"\nUpdating titles for {len(matches)} item(s) …")
    updated = errors = 0
    for item, new_title in matches:
        key = item["data"]["key"]
        try:
            item["data"]["title"] = new_title
            zot.update_item(item)
            print(f"  ✓ Updated: {key}")
            updated += 1
            time.sleep(0.15)
        except Exception as exc:
            print(f"  ✗ Failed : {key} - {exc}")
            errors += 1

    print(f"\nDone. Updated: {updated}  Errors: {errors}")
