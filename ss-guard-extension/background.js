var API_URL = 'https://srv1563194.hstgr.cloud:4443';
var API_TOKEN = 'Xg5ci39x_pIQXQzSHPkZtmbpZvL0b_q-sPnRD3kb0vQ';

// Badge management
chrome.storage.onChanged.addListener(function(changes) {
  if (changes.ssUnseenCount) {
    updateBadge(changes.ssUnseenCount.newValue || 0);
  }
});

function updateBadge(count) {
  if (count > 0) {
    chrome.action.setBadgeText({ text: String(count) });
    chrome.action.setBadgeBackgroundColor({ color: '#e8353e' });
  } else {
    chrome.action.setBadgeText({ text: '' });
  }
}

// Set badge on startup
chrome.storage.local.get(['ssUnseenCount'], function(data) {
  updateBadge(data.ssUnseenCount || 0);
});

// Use chrome.alarms for reliable recurring polls (MV3 kills setInterval)
chrome.alarms.create('shade-poll', { periodInMinutes: 1 });

chrome.alarms.onAlarm.addListener(function(alarm) {
  if (alarm.name === 'shade-poll') pollShade();
});

// Also poll on install/update
chrome.runtime.onInstalled.addListener(function() {
  pollShade();
});

// Poll on service worker wake
pollShade();

function pollShade() {
  chrome.storage.local.get(['ssLastSeen', 'ssUnseenCount', 'ssSeenIds'], function(data) {
    var since = data.ssLastSeen || '';
    var url = API_URL + '/api/phantom-logs/?token=' + encodeURIComponent(API_TOKEN);
    if (since) url += '&since=' + encodeURIComponent(since);

    fetch(url).then(function(r) { return r.json(); }).then(function(logs) {
      if (!logs || !logs.length) return;

      var seenIds = data.ssSeenIds || [];
      var newLogs = logs.filter(function(l) { return seenIds.indexOf(l.id) === -1; });
      if (!newLogs.length) return;

      // Update storage
      var newest = newLogs[0].created_at;
      var d = new Date(newest.replace(' ', 'T') + '-07:00');
      d.setSeconds(d.getSeconds() + 1);
      var bumped = d.toISOString();
      var updatedIds = newLogs.map(function(l) { return l.id; }).concat(seenIds).slice(0, 200);
      var unseen = (data.ssUnseenCount || 0) + newLogs.length;
      chrome.storage.local.set({ ssLastSeen: bumped, ssUnseenCount: unseen, ssSeenIds: updatedIds });

      // Send to one SoStocked tab for toast display
      chrome.tabs.query({ url: 'https://app.sostocked.com/*' }, function(tabs) {
        if (tabs.length > 0) {
          chrome.tabs.sendMessage(tabs[0].id, { type: 'shade-alerts', logs: newLogs });
        }
      });
    }).catch(function(e) {
      console.log('[SoStocked Guard] poll error:', e.message);
    });
  });
}
