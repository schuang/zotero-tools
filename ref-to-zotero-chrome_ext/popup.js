const $ = id => document.getElementById(id);
let resolvedItems = []; // holds resolved items between "Complete" and "Add to Zotero"

$('options-link').addEventListener('click', e => {
  e.preventDefault();
  chrome.runtime.openOptionsPage();
});

// ── Reference parsing ──────────────────────────────────────────────────────

// Split raw textarea input into individual reference strings.
// Primary delimiter: blank lines. Fallback: numbered list markers (1. / [1]).
function splitRefs(text) {
  const byBlank = text.split(/\n\s*\n/).map(s => s.trim()).filter(Boolean);
  if (byBlank.length > 1) return byBlank;
  const lines = text.split('\n');
  const refs = [];
  let cur = '';
  for (const line of lines) {
    if (/^\s*[\[\(]?\d+[\]\)\.]\s+/.test(line) && cur.trim()) {
      refs.push(cur.trim());
      cur = line;
    } else {
      cur += (cur ? ' ' : '') + line.trim();
    }
  }
  if (cur.trim()) refs.push(cur.trim());
  return refs.length ? refs : [text.trim()];
}

// ── Identifier extraction ──────────────────────────────────────────────────

// Extract DOI using the standard "10.XXXX/..." pattern.
function extractDOI(ref) {
  const m = ref.match(/\b(10\.\d{4,}\/[^\s?#&]+)/);
  return m ? m[1].replace(/[.,;)\]]+$/, '') : null;
}

// Extract ISBN-10 or ISBN-13 (with or without explicit "ISBN:" prefix).
function extractISBN(ref) {
  const m = ref.match(/(?:ISBN[-:]?\s*)?((?:97[89])?\d[\d -]{9,16}\d)/i);
  if (!m) return null;
  const isbn = m[1].replace(/[\s-]/g, '');
  return (isbn.length === 10 || isbn.length === 13) ? isbn : null;
}

// ── External API calls ─────────────────────────────────────────────────────

// Fetch full metadata from CrossRef by exact DOI.
async function fetchCrossRef(doi) {
  const r = await fetch(`https://api.crossref.org/works/${encodeURIComponent(doi)}`);
  if (!r.ok) return null;
  const d = (await r.json()).message;
  return crossrefToZotero(d);
}

// Search CrossRef by free text when no DOI is known; takes the top result.
async function searchCrossRef(query) {
  const r = await fetch(
    `https://api.crossref.org/works?query=${encodeURIComponent(query)}&rows=1&select=DOI,title,author,published,container-title,volume,issue,page,publisher,type,ISBN,ISSN`
  );
  if (!r.ok) return null;
  const items = (await r.json()).message.items;
  if (!items?.length) return null;
  return crossrefToZotero(items[0]);
}

// Fetch book metadata from Open Library by ISBN.
// Author names require a second request per author key.
async function fetchOpenLibrary(isbn) {
  const r = await fetch(`https://openlibrary.org/isbn/${isbn}.json`);
  if (!r.ok) return null;
  const d = await r.json();
  let authors = [];
  if (d.authors) {
    authors = await Promise.all(d.authors.map(async a => {
      const ar = await fetch(`https://openlibrary.org${a.key}.json`);
      if (!ar.ok) return { firstName: '', lastName: a.key };
      const ad = await ar.json();
      const parts = (ad.name || '').split(' ');
      return { firstName: parts.slice(0, -1).join(' '), lastName: parts.at(-1) || '' };
    }));
  }
  return {
    itemType: 'book',
    title: d.title || '',
    authors,
    publisher: d.publishers?.[0] || '',
    place: d.publish_places?.[0] || '',
    date: (d.publish_date || '').match(/\d{4}/)?.[0] || '', // extract year from free-text date
    ISBN: isbn,
    numPages: d.number_of_pages ? String(d.number_of_pages) : ''
  };
}

// Decode HTML entities (e.g. "&amp;" → "&", "&lt;" → "<") returned by CrossRef.
function decodeEntities(str) {
  if (!str) return str;
  return str
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&apos;/g, "'");
}

// Normalize a CrossRef API response into our internal item format.
function crossrefToZotero(d) {
  const authors = (d.author || []).map(a => ({
    firstName: a.given || '',
    lastName: a.family || a.name || '',
    creatorType: 'author'
  }));
  // For books CrossRef often misclassifies the sole author as editor.
  // When there are no authors at all, promote editors to authors for books
  // but keep them flagged so the display can note the source ambiguity.
  const editors = (d.editor || []).map(a => ({
    firstName: a.given || '',
    lastName: a.family || a.name || '',
    creatorType: 'editor'
  }));
  const type = d.type || '';
  const isBookType = type.includes('book') || type === 'monograph';
  // For books with no explicit authors, fall back to editors but mark them
  // so formatItem can note the ambiguity without losing the name.
  const creators = authors.length ? authors
    : (isBookType && editors.length) ? editors.map(e => ({ ...e, _fromEditor: true }))
    : editors;
  const isBookChapter = type === 'book-chapter';
  const isBook = !isBookChapter && isBookType;
  // date-parts is [[year, month, day]] — take only the year element
  const date = String(d.published?.['date-parts']?.[0]?.[0] ||
               d['published-print']?.['date-parts']?.[0]?.[0] || '');
  return {
    itemType: isBook ? 'book' : isBookChapter ? 'bookSection' : 'journalArticle',
    title: decodeEntities((d.title?.[0] || '').replace(/<[^>]+>/g, '')), // strip HTML tags, then decode entities
    authors: creators,
    date,
    DOI: d.DOI || '',
    URL: d.URL || '',
    publisher: decodeEntities(d.publisher || ''),
    // For books, container-title is the series name, not a journal
    publicationTitle: (!isBook && !isBookChapter) ? decodeEntities(d['container-title']?.[0] || '') : '',
    seriesTitle: isBook ? decodeEntities(d['container-title']?.[0] || '') : '',
    bookTitle: isBookChapter ? decodeEntities(d['container-title']?.[0] || '') : '',
    volume: d.volume || '',
    issue: (!isBook) ? (d.issue || '') : '',
    pages: d.page || '',
    ISBN: (isBook || isBookChapter) ? (d.ISBN?.[0] || '').replace(/^ISBN:/, '') : '',
    ISSN: (!isBook && !isBookChapter) ? (d.ISSN?.[0] || '') : ''
  };
}

// ── Resolve a single reference ─────────────────────────────────────────────

// Resolution priority: DOI (exact CrossRef lookup) → ISBN (Open Library) → text search (CrossRef).
async function resolveOne(ref) {
  const doi = extractDOI(ref);
  if (doi) {
    const item = await fetchCrossRef(doi);
    if (item) return item;
  }
  const isbn = extractISBN(ref);
  if (isbn) {
    const item = await fetchOpenLibrary(isbn);
    if (item) return item;
  }
  const item = await searchCrossRef(ref);
  if (item) return item;
  // Could not resolve — return raw text so the user can still submit manually
  return { itemType: 'journalArticle', title: ref, authors: [], _unresolved: true };
}

// ── Display ────────────────────────────────────────────────────────────────

// Render a resolved item as an HTML card shown between Complete and Submit.
function formatItem(item) {
  const isBook = item.itemType === 'book';
  const authStr = item.authors.map(a => {
    const name = [a.lastName, a.firstName].filter(Boolean).join(', ');
    // _fromEditor means CrossRef stored this person as editor but we promoted
    // them to author (common CrossRef data issue for single-author books)
    return a._fromEditor ? `${name} ⚠ listed as editor in CrossRef` : a.creatorType === 'editor' ? `${name} (ed.)` : name;
  }).join('; ');
  const fields = [
    item.title && `<span class="title">${item.title}</span>`,
    authStr && `Authors: ${authStr}`,
    item.publicationTitle && `Journal: ${item.publicationTitle}`,
    isBook && item.seriesTitle && `Series: ${item.seriesTitle}`,
    item.publisher && `Publisher: ${item.publisher}`,
    item.date && `Date: ${item.date}`,
    item.volume && `Vol: ${item.volume}`,
    item.issue && `Issue: ${item.issue}`,
    item.pages && `Pages: ${item.pages}`,
    item.DOI && `DOI: ${item.DOI}`,
    item.ISBN && `ISBN: ${item.ISBN}`,
    item.ISSN && `ISSN: ${item.ISSN}`
  ].filter(Boolean);
  return `<div class="ref-card${item._unresolved ? ' error' : ''}">
    <div class="meta">${fields.join('<br>')}</div>
    ${item._unresolved ? '<em>⚠ Could not fully resolve — will submit as-is</em>' : ''}
  </div>`;
}

// ── Zotero API ─────────────────────────────────────────────────────────────

// Build the JSON payload expected by the Zotero API.
// Empty strings are stripped; arrays/objects (tags, collections, relations) are always included
// as they are required by Zotero's PUT schema.
function toZoteroPayload(item) {
  const creators = item.authors.map(a => ({
    // _fromEditor means CrossRef misclassified an author as editor — submit as author
    creatorType: a._fromEditor ? 'author' : (a.creatorType || 'author'),
    firstName: a.firstName,
    lastName: a.lastName
  }));
  const isBook = item.itemType === 'book';
  const isBookSection = item.itemType === 'bookSection';
  const base = {
    itemType: item.itemType,
    title: item.title,
    creators,
    date: (item.date || '').slice(0, 4),
    url: item.URL || '',
    DOI: (!isBook && !isBookSection) || item.DOI ? (item.DOI || '') : undefined,
    ISBN: (isBook || isBookSection) ? (item.ISBN || '') : undefined,
    ISSN: (!isBook && !isBookSection) ? (item.ISSN || '') : undefined,
    publisher: item.publisher || '',
    publicationTitle: (!isBook && !isBookSection) ? (item.publicationTitle || '') : undefined,
    seriesTitle: isBook ? (item.seriesTitle || '') : undefined,
    bookTitle: isBookSection ? (item.bookTitle || item.publicationTitle || '') : undefined,
    volume: item.volume || '',
    issue: (!isBook && !isBookSection) ? (item.issue || '') : undefined,
    pages: item.pages || '',
    place: item.place || '',
    numPages: item.numPages || '',
    tags: [],
    collections: [],
    relations: {}
  };
  return Object.fromEntries(Object.entries(base).filter(([, v]) => v !== undefined && v !== ''));
}

// Search by first author last name + year (both indexed by Zotero's titleCreatorYear mode),
// then verify exact DOI/ISBN. The combined query naturally returns very few results.
async function findExisting(userId, apiKey, item) {
  if (!item.DOI && !item.ISBN) return [];
  const lastName = item.authors?.[0]?.lastName || '';
  const year = (item.date || '').slice(0, 4);
  const query = [lastName, year].filter(Boolean).join(' ');
  if (!query) return [];
  const r = await fetch(
    `https://api.zotero.org/users/${userId}/items?q=${encodeURIComponent(query)}&qmode=titleCreatorYear`,
    { headers: { 'Zotero-API-Key': apiKey, 'Zotero-API-Version': '3' } }
  );
  if (!r.ok) return [];
  const data = await r.json();
  if (!Array.isArray(data)) return [];
  const normDOI = (item.DOI || '').toLowerCase();
  const normISBN = (item.ISBN || '').replace(/[\s-]/g, '');
  return data
    .filter(({ data: d }) => {
      if (normDOI && (d.DOI || '').toLowerCase() === normDOI) return true;
      if (normISBN && (d.ISBN || '').replace(/[\s-]/g, '') === normISBN) return true;
      return false;
    })
    .map(m => ({ key: m.key, version: m.version }));
}

// Submit items to Zotero.
// Normal mode: skip duplicates (matched by DOI/ISBN).
// Force mode: PUT-replace the first match, DELETE any extra duplicates, POST new items.
async function submitToZotero(userId, apiKey, items, force = false) {
  const headers = { 'Zotero-API-Key': apiKey, 'Zotero-API-Version': '3', 'Content-Type': 'application/json' };
  const existingList = await Promise.all(items.map(item => findExisting(userId, apiKey, item)));

  let added = 0, replaced = 0, skipped = 0;

  await Promise.all(items.map(async (item, i) => {
    const matches = existingList[i];
    if (matches.length && !force) { skipped++; return; }    const payload = toZoteroPayload(item);
    if (matches.length && force) {
      // Replace the first matching record in-place
      const r = await fetch(`https://api.zotero.org/users/${userId}/items/${matches[0].key}`, {
        method: 'PUT',
        headers: { ...headers, 'If-Unmodified-Since-Version': String(matches[0].version) },
        body: JSON.stringify(payload)
      });
      if (!r.ok) throw new Error(`Zotero PUT error: ${r.status} ${await r.text()}`);
      // Remove any additional duplicates (e.g. from prior failed force-inserts)
      await Promise.all(matches.slice(1).map(m =>
        fetch(`https://api.zotero.org/users/${userId}/items/${m.key}`, {
          method: 'DELETE',
          headers: { 'Zotero-API-Key': apiKey, 'Zotero-API-Version': '3', 'If-Unmodified-Since-Version': String(m.version) }
        })
      ));
      replaced++;
    } else {
      const r = await fetch(`https://api.zotero.org/users/${userId}/items`, {
        method: 'POST',
        headers,
        body: JSON.stringify([payload])
      });
      if (!r.ok) throw new Error(`Zotero POST error: ${r.status}`);
      const result = await r.json();
      const failed = result.failed && Object.values(result.failed);
      if (failed?.length) throw new Error(`Zotero POST failed: ${failed[0].message}`);
      added++;
    }
  }));

  return { added, replaced, skipped, matches: existingList.map(m => m.length) };
}

// ── Button handlers ────────────────────────────────────────────────────────

// "Complete References": resolve each pasted reference via CrossRef / Open Library.
$('complete-btn').addEventListener('click', async () => {
  const text = $('input').value.trim();
  if (!text) return;
  $('status').textContent = 'Resolving…';
  $('complete-btn').disabled = true;
  $('submit-btn').disabled = true;
  $('results').innerHTML = '';
  resolvedItems = [];

  try {
    const refs = splitRefs(text);
    resolvedItems = await Promise.all(refs.map(resolveOne));
    $('results').innerHTML = resolvedItems.map(formatItem).join('');
    $('submit-btn').disabled = false;
    $('status').textContent = `Resolved ${resolvedItems.length} reference(s).`;
  } catch (err) {
    $('status').textContent = `Error: ${err.message}`;
  } finally {
    $('complete-btn').disabled = false;
  }
});

// "Add to Zotero": check credentials, then submit with optional force-insert.
$('submit-btn').addEventListener('click', async () => {
  chrome.storage.sync.get(['zoteroUserId', 'zoteroApiKey'], async data => {
    const { zoteroUserId, zoteroApiKey } = data;
    if (!zoteroUserId || !zoteroApiKey) {
      $('status').textContent = 'Please set Zotero credentials in Settings first.';
      return;
    }
    $('submit-btn').disabled = true;
    $('status').textContent = 'Checking for duplicates…';
    try {
      const force = $('force-insert').checked;
      const { added, replaced, skipped, matches } = await submitToZotero(zoteroUserId, zoteroApiKey, resolvedItems, force);
      const parts = [];
      if (added) parts.push(`✓ ${added} added`);
      if (replaced) parts.push(`✓ ${replaced} replaced`);
      if (skipped) parts.push(`${skipped} skipped (duplicate)`);
      $('status').textContent = parts.join(' · ') || `✓ Done (force=${force}, matches=${matches})`;
      $('input').value = '';
      $('results').innerHTML = '';
      resolvedItems = [];
    } catch (err) {
      $('status').textContent = `Error: ${err.message}`;
      $('submit-btn').disabled = false;
    }
  });
});
