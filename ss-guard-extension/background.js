// Update badge when unseen count changes
chrome.storage.onChanged.addListener(function(changes) {
  if (changes.ssUnseenCount) {
    var count = changes.ssUnseenCount.newValue || 0;
    if (count > 0) {
      chrome.action.setBadgeText({ text: String(count) });
      chrome.action.setBadgeBackgroundColor({ color: '#e8353e' });
    } else {
      chrome.action.setBadgeText({ text: '' });
    }
  }
});

// Set badge on startup from stored value
chrome.storage.local.get(['ssUnseenCount'], function(data) {
  var count = data.ssUnseenCount || 0;
  if (count > 0) {
    chrome.action.setBadgeText({ text: String(count) });
    chrome.action.setBadgeBackgroundColor({ color: '#e8353e' });
  }
});
