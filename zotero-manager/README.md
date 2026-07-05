# Zotero Library Manager

Python-based maintenance tools for cleaning and normalising Zotero online libraries.

## Features

### 1. **add-url** - Add URL from DOI
Scans your library for journal articles matching a required DOI, then fills `URL` as `URL_PREFIX/DOI` (default prefix: `https://doi.org`). Existing URL values are overwritten when `--apply` is used. DOIs containing `arxiv` in any case are skipped.

- Prints metadata and the would-be URL for matched items
- Requires explicit DOI matching with `--doi`
- Supports custom URL prefixes with `--url-prefix`
- Dry-run by default; use `--apply` to write changes

### 2. **clear-extra** - Clear Extra field
Scans your library for items whose `Extra` field starts with a configurable prefix (default: `"LLMKB SHA256"`) and clears the field.

- Prints metadata (author, title, date, venue) for matched items
- Supports custom prefix matching with `--prefix`
- Dry-run by default; use `--apply` to write changes

### 3. **fix-titles** - Normalise ALL-CAPS titles
Finds items with titles in ALL-CAPS and converts them to proper case:

- **Sentence case** for articles, preprints, conference papers, reports
- **Title case** for books, book sections, theses, encyclopedias
- **Preserves acronyms** ≤ 4 characters (DNA, HIV, NLP, fMRI, etc.)
- Respects sub-title boundaries (capitalises after `:`, `---`, `-`)

### 4. **all** - Run all tasks
Executes tasks that have default arguments sequentially. Tasks requiring explicit options, such as `add-url --doi`, are skipped. Each task runs in dry-run mode unless `--apply` is specified.

---

## Installation

### Prerequisites
- Python 3.10+ (WSL Fedora or any Linux/macOS environment)
- `uv` (Python package runner) or standard `pip`

### Setup

1. **Clone or copy the project:**
   ```bash
   cd ~/zotero-clear-extra
   ```

2. **Install dependencies:**
   
   Using `uv` (recommended):
   ```bash
   uv venv
   uv pip install pyzotero
   ```
   
   Or with standard `pip`:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install pyzotero
   ```

3. **Configure credentials:**

   Set environment variables (or edit `zotero_tasks/common.py`):
   ```bash
   export ZOTERO_USER_ID="your_user_id"
   export ZOTERO_API_KEY="your_api_key_here"
   ```

---

## Usage

### Basic commands

```bash
# Show help
python zotero_manager.py --help

# Run a specific task (dry run)
python zotero_manager.py clear-extra
python zotero_manager.py fix-titles
python zotero_manager.py add-url --doi "10.1000/example"

# Apply changes (writes to Zotero)
python zotero_manager.py clear-extra --apply
python zotero_manager.py fix-titles --apply
python zotero_manager.py add-url --doi "10.1000/example" --apply

# Run all tasks at once
python zotero_manager.py all --apply
```

### Task-specific options

#### clear-extra
```bash
# Use a custom prefix
python zotero_manager.py clear-extra --prefix "MY PREFIX"

# Show help for this task
python zotero_manager.py clear-extra --help
```

#### add-url
```bash
# Match a specific DOI
python zotero_manager.py add-url --doi "10.1000/example"

# Use a custom URL prefix
python zotero_manager.py add-url --doi "10.1000/example" --url-prefix "https://doi.org"

# Show help for this task
python zotero_manager.py add-url --help
```

#### fix-titles
```bash
# Show help for this task
python zotero_manager.py fix-titles --help
```

---

## Project Structure

```
zotero-clear-extra/
├── zotero_manager.py          # Main CLI entry point with subcommand routing
├── zotero_tasks/              # Task modules
│   ├── __init__.py            # Package exports
│   ├── common.py              # Shared utilities (connect, iter_items, format_metadata)
│   ├── add_url.py             # Feature 1: add URL from DOI
│   ├── clear_extra.py         # Feature 2: clear Extra field
│   └── fix_titles.py          # Feature 3: normalise ALL-CAPS titles
└── README.md                  # This file
```

### Architecture

- **Modular design:** Each feature lives in its own module under `zotero_tasks/`
- **Shared utilities:** Common code (API connection, pagination, metadata formatting) in `common.py`
- **Subcommand interface:** Each module exposes:
  - `add_arguments(parser)` - registers CLI flags
  - `run(args)` - executes the task
- **Easy extensibility:** Add new features by creating a new module and registering it in `TASKS` dict in `zotero_manager.py`

---

## Adding New Features

1. Create a new module: `zotero_tasks/my_feature.py`

2. Implement the interface:
   ```python
   """my_feature.py - brief description"""
   
   import time
   from .common import connect, iter_items, format_metadata
   
   def add_arguments(parser):
       parser.add_argument(
           "--apply",
           action="store_true",
           help="Write changes to Zotero. Without this flag, dry run.",
       )
       # Add feature-specific arguments here
   
   def run(args):
       dry_run = not args.apply
       print(f"Running my_feature in {'APPLY' if not dry_run else 'DRY RUN'} mode")
       
       zot = connect()
       for item in iter_items(zot):
           # Your logic here
           pass
   ```

3. Register in `zotero_manager.py`:
   ```python
   from zotero_tasks import clear_extra, fix_titles, my_feature
   
   TASKS = {
       "clear-extra": clear_extra,
       "fix-titles": fix_titles,
       "my-feature": my_feature,  # Add this line
   }
   ```

4. Run:
   ```bash
   python zotero_manager.py my-feature --apply
   ```

---

## Environment Variables

| Variable          | Description                        | Default      |
|-------------------|------------------------------------|--------------|
| `ZOTERO_USER_ID`  | Your numeric Zotero user ID        | (required)   |
| `ZOTERO_API_KEY`  | Your Zotero API key                | (required)   |

Set these in your shell or edit the defaults in `zotero_tasks/common.py`.

---

## Troubleshooting

### `pyzotero.errors.UnsupportedParamsError`
- Make sure your API key has write permissions
- Check that `ZOTERO_USER_ID` matches your account

### Rate limiting
- The script includes a 0.15-second delay between API writes to stay within Zotero's rate limits
- If you hit rate limits, increase the `time.sleep()` value in the task modules

### Acronym preservation not working
- Acronyms are detected by length (≤ 4 chars) and all-caps original
- Longer acronyms (e.g., `COVID`, `HTTPS`) are treated as normal words and converted to `Covid`, `Https`
- To preserve specific terms, edit the `_is_acronym()` function in `fix_titles.py`

---

## License

This is a personal utility script. Use freely, modify as needed.
