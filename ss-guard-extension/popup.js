(function() {
  'use strict';

  var listEl = document.getElementById('list');
  var badgeEl = document.getElementById('badge');
  var urlInput = document.getElementById('api-url');
  var tokenInput = document.getElementById('api-token');

  // Load settings
  chrome.storage.local.get(['ssApiUrl', 'ssApiToken', 'ssUnseenCount'], function(data) {
    urlInput.value = data.ssApiUrl || '';
    tokenInput.value = data.ssApiToken || '';
    badgeEl.textContent = data.ssUnseenCount || 0;
    fetchLogs(data.ssApiUrl, data.ssApiToken);
  });

  // Save settings on change
  urlInput.addEventListener('change', function() {
    chrome.storage.local.set({ ssApiUrl: urlInput.value.replace(/\/+$/, '') });
  });
  tokenInput.addEventListener('change', function() {
    chrome.storage.local.set({ ssApiToken: tokenInput.value });
  });

  // Mark all read
  document.getElementById('mark-read').addEventListener('click', function() {
    chrome.storage.local.set({ ssUnseenCount: 0 });
    badgeEl.textContent = '0';
  });

  // Refresh
  document.getElementById('refresh').addEventListener('click', function() {
    chrome.storage.local.get(['ssApiUrl', 'ssApiToken'], function(data) {
      fetchLogs(data.ssApiUrl, data.ssApiToken);
    });
  });

  function fetchLogs(apiUrl, token) {
    if (!apiUrl || !token) {
      listEl.textContent = '';
      var msg = document.createElement('div');
      msg.className = 'empty';
      msg.textContent = '\u041D\u0430\u0441\u0442\u0440\u043E\u0439\u0442\u0435 URL \u0438 \u0442\u043E\u043A\u0435\u043D \u043F\u043E-\u0434\u043E\u043B\u0443.';
      listEl.appendChild(msg);
      return;
    }

    var since = new Date(Date.now() - 72 * 3600 * 1000).toISOString();
    var url = apiUrl + '/api/phantom-logs/?token=' + encodeURIComponent(token) + '&since=' + encodeURIComponent(since);

    fetch(url)
      .then(function(r) { return r.json(); })
      .then(function(logs) { renderLogs(logs); })
      .catch(function(e) {
        listEl.textContent = '';
        var msg = document.createElement('div');
        msg.className = 'empty';
        msg.textContent = '\u0413\u0440\u0435\u0448\u043A\u0430: ' + e.message;
        listEl.appendChild(msg);
      });
  }

  function renderLogs(logs) {
    listEl.textContent = '';
    if (!logs || !logs.length) {
      var msg = document.createElement('div');
      msg.className = 'empty';
      msg.textContent = '\u041D\u044F\u043C\u0430 phantom \u0430\u043B\u0435\u0440\u0442\u0438 \u0437\u0430 \u043F\u043E\u0441\u043B\u0435\u0434\u043D\u0438\u0442\u0435 72 \u0447\u0430\u0441\u0430.';
      listEl.appendChild(msg);
      return;
    }

    logs.forEach(function(log) {
      var entry = document.createElement('div');
      entry.className = 'entry';

      var asin = document.createElement('div');
      asin.className = 'entry-asin';
      asin.textContent = log.asin + '  #' + log.shipment_id;
      entry.appendChild(asin);

      var detail = document.createElement('div');
      detail.className = 'entry-detail';
      var shadeSpan = document.createElement('span');
      shadeSpan.className = 'entry-shade';
      shadeSpan.textContent = 'shade: ' + (log.shade > 0 ? '+' : '') + log.shade;
      detail.appendChild(shadeSpan);
      detail.appendChild(document.createTextNode('  |  param: ' + log.param_diff + '  real: ' + log.real_diff));
      entry.appendChild(detail);

      var warehouse = document.createElement('div');
      warehouse.className = 'entry-user';
      warehouse.textContent = log.warehouse + ' \u2014 ' + log.user;
      entry.appendChild(warehouse);

      var time = document.createElement('div');
      time.className = 'entry-time';
      time.textContent = relativeTime(log.created_at);
      entry.appendChild(time);

      listEl.appendChild(entry);
    });
  }

  function relativeTime(dateStr) {
    if (!dateStr) return '';
    var d = new Date(dateStr.replace(' ', 'T') + '-07:00');
    var diff = Math.floor((Date.now() - d.getTime()) / 60000);
    if (diff < 1) return '\u043F\u0440\u0435\u0434\u0438 \u043C\u0430\u043B\u043A\u043E';
    if (diff < 60) return '\u043F\u0440\u0435\u0434\u0438 ' + diff + ' \u043C\u0438\u043D.';
    var hours = Math.floor(diff / 60);
    if (hours < 24) return '\u043F\u0440\u0435\u0434\u0438 ' + hours + ' \u0447.';
    return '\u043F\u0440\u0435\u0434\u0438 ' + Math.floor(hours / 24) + ' \u0434\u043D.';
  }
})();
