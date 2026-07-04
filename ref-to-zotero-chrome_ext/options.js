const $ = id => document.getElementById(id);

chrome.storage.sync.get(['zoteroUserId', 'zoteroApiKey'], data => {
  $('user-id').value = data.zoteroUserId || '';
  $('api-key').value = data.zoteroApiKey || '';
});

$('save-btn').addEventListener('click', () => {
  chrome.storage.sync.set({
    zoteroUserId: $('user-id').value.trim(),
    zoteroApiKey: $('api-key').value.trim()
  }, () => {
    $('status').textContent = 'Saved.';
    setTimeout(() => { $('status').textContent = ''; }, 2000);
  });
});
