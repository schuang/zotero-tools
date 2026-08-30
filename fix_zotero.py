#!/usr/bin/env python3
"""
fix_zotero.py

Processes bibliography records in mylib.json:
1. Queries CrossRef (DOI-first, falling back to title search).
2. Compares metadata (normalized title similarity >= 0.75 and first author last name match).
3. If valid:
   - Deletes original item from Zotero.
   - Inserts the fresh record derived from CrossRef into Zotero.
   - Saves record to success.json.
4. If different, not found, or error:
   - Leaves original item in Zotero untouched.
   - Saves record to unsure.json with reason and CrossRef data.
5. In all cases: len(success.json) + len(unsure.json) == len(mylib.json).
"""

import os
import sys
import json
import time
import re
import html
import argparse
import difflib
from typing import Dict, Any, Optional, Tuple, List
import requests

# ---------------------------------------------------------------------------
# Configuration & Environment
# ---------------------------------------------------------------------------

def load_env(env_path: str = ".env") -> Dict[str, str]:
    """Loads key-value pairs from a .env file if it exists."""
    env = {}
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip("'\"")
    return env


# ---------------------------------------------------------------------------
# Text Normalization & Similarity Checking
# ---------------------------------------------------------------------------

def normalize_text(text: Optional[str]) -> str:
    """Normalizes a string by unescaping HTML, stripping tags, removing punctuation, and lowercasing."""
    if not text:
        return ""
    text = html.unescape(str(text))
    text = re.sub(r"<[^>]+>", " ", text)          # Strip HTML/XML tags
    text = re.sub(r"[{}\\_^$]", " ", text)        # Strip LaTeX/BibTeX special formatting
    text = re.sub(r"[^a-zA-Z0-9\s]", " ", text)   # Remove punctuation
    text = re.sub(r"\s+", " ", text)              # Collapse whitespace
    return text.strip().lower()


def compute_title_similarity(title1: str, title2: str) -> float:
    """Computes sequence similarity between two normalized titles."""
    t1 = normalize_text(title1)
    t2 = normalize_text(title2)
    if not t1 or not t2:
        return 0.0
    return difflib.SequenceMatcher(None, t1, t2).ratio()


def extract_first_author_lastname(authors_or_creators: Any) -> str:
    """Extracts normalized last name of the first author from various author list formats."""
    if not authors_or_creators or not isinstance(authors_or_creators, list):
        return ""
    first = authors_or_creators[0]
    if isinstance(first, dict):
        last = first.get("family") or first.get("lastName") or first.get("name") or ""
        if not last and "given" in first and not first.get("family"):
            parts = str(first["given"]).strip().split()
            if parts:
                last = parts[-1]
        return normalize_text(last)
    elif isinstance(first, str):
        parts = first.split(",")
        return normalize_text(parts[0])
    return ""


def format_authors_summary(authors_or_creators: Any) -> str:
    """Formats authors into a readable short string like 'Dongjoo Kim, Haecheon Choi'."""
    if not authors_or_creators or not isinstance(authors_or_creators, list):
        return "(none)"
    names = []
    for a in authors_or_creators:
        if isinstance(a, dict):
            given = a.get("given") or a.get("firstName") or ""
            family = a.get("family") or a.get("lastName") or a.get("name") or ""
            if given and family:
                names.append(f"{given} {family}")
            elif family:
                names.append(family)
            elif given:
                names.append(given)
        elif isinstance(a, str):
            names.append(a)
    return ", ".join(names) if names else "(none)"


def check_author_match(orig_authors: Any, crossref_authors: Any) -> bool:
    """
    Checks if first author last names match.
    If either source does not provide author information, author check is considered satisfied.
    """
    a1 = extract_first_author_lastname(orig_authors)
    a2 = extract_first_author_lastname(crossref_authors)
    if not a1 or not a2:
        return True  # Lenient if author is missing in either
    
    # Exact match, prefix match, or high similarity
    if a1 == a2 or a1.startswith(a2) or a2.startswith(a1):
        return True
    
    sim = difflib.SequenceMatcher(None, a1, a2).ratio()
    return sim >= 0.75




# ---------------------------------------------------------------------------
# CrossRef Client & Transformer
# ---------------------------------------------------------------------------

class CrossRefClient:
    def __init__(self, delay: float = 0.5, mailto: str = "user@example.com"):
        self.delay = delay
        self.headers = {
            "User-Agent": f"ZoteroFixer/1.0 (mailto:{mailto})"
        }

    def get_by_doi(self, doi: str) -> Optional[Dict[str, Any]]:
        """Queries CrossRef by DOI."""
        clean_doi = doi.strip()
        url = f"https://api.crossref.org/works/{clean_doi}"
        time.sleep(self.delay)
        try:
            resp = requests.get(url, headers=self.headers, timeout=15)
            if resp.status_code == 200:
                return resp.json().get("message")
        except Exception as e:
            print(f"    [CrossRef Error] DOI lookup failed: {e}", file=sys.stderr)
        return None

    def search_by_title(self, title: str) -> Optional[Dict[str, Any]]:
        """Queries CrossRef by title keyword search."""
        clean_title = normalize_text(title)
        if not clean_title:
            return None
        url = "https://api.crossref.org/works"
        params = {"query.title": clean_title, "rows": 1}
        time.sleep(self.delay)
        try:
            resp = requests.get(url, headers=self.headers, params=params, timeout=15)
            if resp.status_code == 200:
                items = resp.json().get("message", {}).get("items", [])
                if items:
                    return items[0]
        except Exception as e:
            print(f"    [CrossRef Error] Title search failed: {e}", file=sys.stderr)
        return None


def crossref_to_zotero_item(msg: Dict[str, Any]) -> Dict[str, Any]:
    """Converts a CrossRef message JSON into a valid Zotero item dictionary."""
    c_type = msg.get("type", "")
    type_map = {
        "journal-article": "journalArticle",
        "book": "book",
        "monograph": "book",
        "book-chapter": "bookSection",
        "book-section": "bookSection",
        "proceedings-article": "conferencePaper",
        "report": "report",
        "posted-content": "preprint",
        "dissertation": "thesis",
        "dataset": "dataset",
    }
    item_type = type_map.get(c_type, "journalArticle")

    # Title
    titles = msg.get("title", [])
    raw_title = titles[0] if titles else ""
    # Clean excessive whitespace/newlines from Crossref title
    title = re.sub(r"\s+", " ", html.unescape(raw_title)).strip()

    # Creators
    creators = []
    for a in msg.get("author", []):
        given = a.get("given", "").strip()
        family = a.get("family", "").strip()
        name = a.get("name", "").strip()
        if family or given:
            creators.append({"creatorType": "author", "firstName": given, "lastName": family})
        elif name:
            creators.append({"creatorType": "author", "name": name})

    # Date
    date_parts = (
        msg.get("published-print")
        or msg.get("published-online")
        or msg.get("issued")
        or msg.get("created")
        or {}
    ).get("date-parts", [])
    date_str = ""
    if date_parts and date_parts[0]:
        parts = date_parts[0]
        date_str = "-".join(f"{p:02d}" if i > 0 else str(p) for i, p in enumerate(parts))

    # Containers and metadata
    containers = msg.get("container-title", [])
    container = containers[0] if containers else ""
    volume = str(msg.get("volume", "")).strip()
    issue = str(msg.get("issue", "")).strip()
    page = str(msg.get("page", "")).strip()
    doi_val = msg.get("DOI", "").strip()
    url_val = msg.get("URL", "").strip() or (f"https://doi.org/{doi_val}" if doi_val else "")
    publisher = msg.get("publisher", "").strip()
    issns = msg.get("ISSN", [])
    issn = issns[0] if issns else ""
    isbns = msg.get("ISBN", [])
    isbn = isbns[0] if isbns else ""

    item_data: Dict[str, Any] = {
        "itemType": item_type,
        "title": title,
        "creators": creators,
        "date": date_str,
        "DOI": doi_val,
        "url": url_val,
    }

    if item_type == "journalArticle":
        item_data["publicationTitle"] = container
        item_data["volume"] = volume
        item_data["issue"] = issue
        item_data["pages"] = page
        item_data["ISSN"] = issn
    elif item_type == "book":
        item_data["publisher"] = publisher
        item_data["ISBN"] = isbn
    elif item_type == "bookSection":
        item_data["bookTitle"] = container
        item_data["publisher"] = publisher
        item_data["pages"] = page
        item_data["ISBN"] = isbn
    elif item_type == "conferencePaper":
        item_data["proceedingsTitle"] = container
        item_data["publisher"] = publisher
        item_data["pages"] = page
        item_data["volume"] = volume
        item_data["issue"] = issue
        item_data["ISBN"] = isbn
    elif item_type == "preprint":
        item_data["repository"] = publisher or container
    elif item_type == "report":
        item_data["institution"] = publisher
        item_data["pages"] = page

    return item_data


# ---------------------------------------------------------------------------
# Zotero API Client
# ---------------------------------------------------------------------------

class ZoteroClient:
    def __init__(self, user_id: str, api_key: str, delay: float = 0.5):
        self.user_id = user_id
        self.api_key = api_key
        self.delay = delay
        self.base_url = f"https://api.zotero.org/users/{user_id}"
        self.headers = {
            "Zotero-API-Version": "3",
            "Zotero-API-Key": api_key,
        }

    def fetch_all_top_items(self) -> List[Dict[str, Any]]:
        """Fetches all top-level items in the user library with pagination."""
        items = []
        start = 0
        limit = 100
        while True:
            time.sleep(self.delay)
            url = f"{self.base_url}/items/top"
            params = {"start": start, "limit": limit}
            resp = requests.get(url, headers=self.headers, params=params, timeout=30)
            if resp.status_code != 200:
                raise RuntimeError(f"Failed to fetch Zotero items: HTTP {resp.status_code} - {resp.text}")
            chunk = resp.json()
            if not chunk:
                break
            items.extend(chunk)
            start += len(chunk)
            if len(chunk) < limit:
                break
        return items

    def delete_item(self, item_key: str, version: int) -> bool:
        """Deletes an item from Zotero using optimistic concurrency header."""
        time.sleep(self.delay)
        url = f"{self.base_url}/items/{item_key}"
        del_headers = dict(self.headers)
        del_headers["If-Unmodified-Since-Version"] = str(version)
        resp = requests.delete(url, headers=del_headers, timeout=20)
        return resp.status_code in (200, 204)

    def create_item(self, item_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Inserts a single new item into Zotero."""
        time.sleep(self.delay)
        url = f"{self.base_url}/items"
        post_headers = dict(self.headers)
        post_headers["Content-Type"] = "application/json"
        resp = requests.post(url, headers=post_headers, json=[item_data], timeout=20)
        if resp.status_code in (200, 201):
            res_json = resp.json()
            successful = res_json.get("successful", {})
            if successful:
                return list(successful.values())[0]
        print(f"    [Zotero Error] Failed to create item: HTTP {resp.status_code} - {resp.text}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Main Orchestrator
# ---------------------------------------------------------------------------

def process_records(
    input_file: str,
    output_success: str,
    output_unsure: str,
    dry_run: bool = False,
    delay: float = 0.5,
    title_sim_threshold: float = 0.75,
):
    # 1. Load Environment & Credentials
    env = load_env(".env")
    api_key = os.environ.get("ZOTERO_API_KEY") or env.get("ZOTERO_API_KEY")
    user_id = os.environ.get("ZOTERO_USER_ID") or env.get("ZOTERO_USER_ID")

    if not api_key or not user_id:
        print("[ERROR] ZOTERO_API_KEY or ZOTERO_USER_ID not found in environment or .env file.", file=sys.stderr)
        sys.exit(1)

    # 2. Load Input Records
    if not os.path.exists(input_file):
        print(f"[ERROR] Input file '{input_file}' not found.", file=sys.stderr)
        sys.exit(1)

    with open(input_file, "r", encoding="utf-8") as f:
        records = json.load(f)

    print(f"[*] Loaded {len(records)} records from {input_file}.")
    print(f"[*] Mode: {'DRY RUN (no Zotero modifications)' if dry_run else 'LIVE RUN'}")
    print(f"[*] Delay between API calls: {delay}s | Title Sim Threshold: {title_sim_threshold}")

    zotero = ZoteroClient(user_id=user_id, api_key=api_key, delay=delay)
    crossref = CrossRefClient(delay=delay)

    # 3. Fetch current Zotero items to build lookup indexes
    print("[*] Fetching existing library items from Zotero...")
    all_zotero_items = zotero.fetch_all_top_items()
    print(f"[*] Retrieved {len(all_zotero_items)} top-level items from Zotero.")

    # Index by DOI and normalized title
    zot_by_doi: Dict[str, Dict[str, Any]] = {}
    zot_by_title: Dict[str, Dict[str, Any]] = {}

    for it in all_zotero_items:
        data = it.get("data", {})
        doi = data.get("DOI", "").strip().lower()
        if doi:
            zot_by_doi[doi] = it
        t_norm = normalize_text(data.get("title", ""))
        if t_norm:
            zot_by_title[t_norm] = it

    success_list: List[Dict[str, Any]] = []
    unsure_list: List[Dict[str, Any]] = []

    # 4. Iterate and Process Records
    for idx, orig in enumerate(records, start=1):
        orig_title = orig.get("title", "")
        orig_doi = orig.get("DOI", "").strip() if orig.get("DOI") else ""
        orig_authors = orig.get("author", [])
        
        print(f"\n[{idx}/{len(records)}] Checking: '{orig_title[:60]}...'")

        # Step A: Find existing Zotero item
        zot_item = None
        if orig_doi and orig_doi.lower() in zot_by_doi:
            zot_item = zot_by_doi[orig_doi.lower()]
        else:
            t_norm = normalize_text(orig_title)
            if t_norm in zot_by_title:
                zot_item = zot_by_title[t_norm]

        if not zot_item:
            print(f"    -> [UNSURE] Corresponding item not found in Zotero library.")
            unsure_list.append({
                "original": orig,
                "reason": "zotero_item_not_found",
                "crossref_result": None
            })
            continue

        # Step B: Query CrossRef (DOI-first, fallback to title)
        cr_msg = None
        if orig_doi:
            cr_msg = crossref.get_by_doi(orig_doi)
        if not cr_msg and orig_title:
            cr_msg = crossref.search_by_title(orig_title)

        if not cr_msg:
            print(f"    -> [UNSURE] Record not found in CrossRef.")
            unsure_list.append({
                "original": orig,
                "reason": "crossref_not_found",
                "crossref_result": None
            })
            continue

        # Step C: Compare Metadata (Title Similarity + First Author match)
        cr_titles = cr_msg.get("title", [])
        cr_title = cr_titles[0] if cr_titles else ""
        cr_authors = cr_msg.get("author", [])

        sim = compute_title_similarity(orig_title, cr_title)
        author_ok = check_author_match(orig_authors, cr_authors)

        if sim < title_sim_threshold:
            print(f"    -> [UNSURE] Title similarity too low ({sim:.2f} < {title_sim_threshold}).")
            print(f"       Orig:     {orig_title}")
            print(f"       CrossRef: {cr_title}")
            unsure_list.append({
                "original": orig,
                "reason": f"title_similarity_low ({sim:.2f})",
                "crossref_result": {
                    "title": cr_title,
                    "DOI": cr_msg.get("DOI"),
                    "author": cr_authors
                }
            })
            continue

        if not author_ok:
            orig_auth_last = extract_first_author_lastname(orig_authors)
            cr_auth_last = extract_first_author_lastname(cr_authors)
            print(f"    -> [UNSURE] Author mismatch: orig='{orig_auth_last}' vs crossref='{cr_auth_last}'.")
            unsure_list.append({
                "original": orig,
                "reason": f"author_mismatch ('{orig_auth_last}' vs '{cr_auth_last}')",
                "crossref_result": {
                    "title": cr_title,
                    "DOI": cr_msg.get("DOI"),
                    "author": cr_authors
                }
            })
            continue

        # Step D: Fresh Zotero Item Creation & Deletion
        new_zotero_data = crossref_to_zotero_item(cr_msg)
        zot_key = zot_item["key"]
        zot_ver = zot_item["version"]

        if dry_run:
            z_data = zot_item.get("data", {})
            print(f"    -> [DRY RUN MATCH] Validated (Title Sim: {sim:.2f})")
            print("       " + "-" * 55)
            print("       [ORIGINAL ZOTERO RECORD]")
            print(f"         Key:        {zot_key}")
            print(f"         Item Type:  {z_data.get('itemType', '')}")
            print(f"         Title:      {z_data.get('title', '')}")
            print(f"         Authors:    {format_authors_summary(z_data.get('creators', []))}")
            print(f"         Date:       {z_data.get('date', '')}")
            print(f"         DOI:        {z_data.get('DOI', '')}")
            print(f"         Container:  {z_data.get('publicationTitle') or z_data.get('bookTitle') or z_data.get('proceedingsTitle') or ''}")
            print("       [WOULD REPLACE WITH (CROSSREF)]")
            print(f"         Item Type:  {new_zotero_data.get('itemType', '')}")
            print(f"         Title:      {new_zotero_data.get('title', '')}")
            print(f"         Authors:    {format_authors_summary(new_zotero_data.get('creators', []))}")
            print(f"         Date:       {new_zotero_data.get('date', '')}")
            print(f"         DOI:        {new_zotero_data.get('DOI', '')}")
            print(f"         Container:  {new_zotero_data.get('publicationTitle') or new_zotero_data.get('bookTitle') or new_zotero_data.get('proceedingsTitle') or ''}")
            print(f"         Volume/Iss: {new_zotero_data.get('volume', '')} / {new_zotero_data.get('issue', '')} (Pages: {new_zotero_data.get('pages', '')})")
            print("       " + "-" * 55)
            success_list.append({
                "original": orig,
                "zotero_original_key": zot_key,
                "zotero_original_data": z_data,
                "new_zotero_data": new_zotero_data
            })

        else:
            # Live replacement
            print(f"    -> Deleting original item (Key: {zot_key})...")
            del_ok = zotero.delete_item(zot_key, zot_ver)
            if not del_ok:
                print(f"    -> [ERROR] Failed to delete original item {zot_key} from Zotero.", file=sys.stderr)
                unsure_list.append({
                    "original": orig,
                    "reason": "zotero_delete_failed",
                    "crossref_result": new_zotero_data
                })
                continue

            print(f"    -> Inserting fresh item into Zotero...")
            created = zotero.create_item(new_zotero_data)
            if created:
                new_key = created.get("key")
                print(f"    -> [SUCCESS] Replaced successfully (New Key: {new_key}).")
                success_list.append({
                    "original": orig,
                    "zotero_original_key": zot_key,
                    "zotero_new_key": new_key,
                    "new_zotero_data": new_zotero_data
                })
            else:
                print(f"    -> [ERROR] Item deletion succeeded, but new item insertion failed!", file=sys.stderr)
                unsure_list.append({
                    "original": orig,
                    "reason": "zotero_insert_failed_after_delete",
                    "crossref_result": new_zotero_data
                })

    # 5. Write Output Files
    print("\n" + "=" * 60)
    print(f"[*] Writing results:")
    print(f"    - Success: {len(success_list)} -> {output_success}")
    print(f"    - Unsure:  {len(unsure_list)} -> {output_unsure}")
    print(f"    - Total:   {len(success_list) + len(unsure_list)} / {len(records)}")
    print("=" * 60)

    with open(output_success, "w", encoding="utf-8") as f:
        json.dump(success_list, f, indent=2, ensure_ascii=False)

    with open(output_unsure, "w", encoding="utf-8") as f:
        json.dump(unsure_list, f, indent=2, ensure_ascii=False)

    assert len(success_list) + len(unsure_list) == len(records), (
        f"Count mismatch: success ({len(success_list)}) + unsure ({len(unsure_list)}) != total ({len(records)})"
    )
    print("[*] Verification passed: len(success.json) + len(unsure.json) == len(mylib.json).")


# ---------------------------------------------------------------------------
# CLI Entrypoint
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Fix Zotero records by validating against CrossRef, deleting old entries, and inserting fresh records."
    )
    parser.add_argument(
        "--input",
        "-i",
        default="mylib.json",
        help="Path to input JSON file (default: mylib.json)",
    )
    parser.add_argument(
        "--success",
        "-s",
        default="success.json",
        help="Path to output success JSON file (default: success.json)",
    )
    parser.add_argument(
        "--unsure",
        "-u",
        default="unsure.json",
        help="Path to output unsure JSON file (default: unsure.json)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes to Zotero database (deletes old records and inserts fresh records). If omitted, runs in safe dry-run mode.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Delay in seconds between API requests (default: 0.5)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.75,
        help="Title similarity threshold between 0.0 and 1.0 (default: 0.75)",
    )

    args = parser.parse_args()

    # Dry-run is enabled by default unless --apply is explicitly specified
    dry_run = not args.apply

    process_records(
        input_file=args.input,
        output_success=args.success,
        output_unsure=args.unsure,
        dry_run=dry_run,
        delay=args.delay,
        title_sim_threshold=args.threshold,
    )


if __name__ == "__main__":
    main()
