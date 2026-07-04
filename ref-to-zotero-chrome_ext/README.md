# Ref to Zotero

A Chrome extension that resolves pasted bibliographic references into complete metadata and adds them to your Zotero online library.

## What it does

1. **Paste** one or more references (plain text, numbered list, or blank-line separated) into the input box.
2. **Complete References** — resolves each reference into full metadata: title, authors, journal/publisher, volume, issue, pages, DOI, ISBN, ISSN, and year.
3. **Review** the resolved records displayed in the popup.
4. **Add to Zotero** — submits the records to your Zotero library, skipping any that already exist (matched by DOI for journal articles, ISBN for books).

The optional **Force insert** checkbox replaces existing records instead of skipping them, and removes any duplicates.

## How it works

### Reference resolution (priority order)

1. **DOI extracted from text** → fetches full metadata directly from [CrossRef](https://api.crossref.org) by exact DOI lookup.
2. **ISBN extracted from text** → fetches book metadata from [Open Library](https://openlibrary.org).
3. **Fallback** → sends the raw reference string as a free-text query to CrossRef and takes the top result.

### Duplicate detection

Zotero's API does not support DOI/ISBN field search. Instead, the extension queries Zotero by the first author's last name and publication year (`qmode=titleCreatorYear`), then confirms an exact DOI or ISBN match in the returned records. This keeps API traffic minimal.

### Zotero submission

- **Normal mode**: new items are POSTed; duplicates are skipped.
- **Force insert**: the matching record is replaced via PUT (using its current version number), and any extra duplicates are deleted.

## Installation

1. Clone or download this repository.
2. Open Chrome and go to `chrome://extensions`.
3. Enable **Developer mode** (toggle in the top-right corner).
4. Click **Load unpacked** and select the `ref-to-zotero` folder.
5. The extension icon appears in the toolbar.

## Configuration

1. Find your Zotero **User ID** and **API Key** at [zotero.org/settings/keys](https://www.zotero.org/settings/keys).  
   - Your numeric User ID appears in the URL when logged in: `zotero.org/users/XXXXXXX`.
   - Create a new API key with **Read/Write** library access.
2. Click the extension icon → **Settings**, enter your User ID and API Key, and click **Save**.

## Files

| File | Purpose |
|------|---------|
| `manifest.json` | Extension config (permissions, entry points) |
| `popup.html/js` | Main UI and all resolution/submission logic |
| `options.html/js` | Settings page for Zotero credentials |
| `styles.css` | UI styling |
