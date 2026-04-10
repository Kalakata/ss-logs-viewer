(function() {
  'use strict';

  var API_URL = 'https://srv1563194.hstgr.cloud:4443';
  var API_TOKEN = 'Xg5ci39x_pIQXQzSHPkZtmbpZvL0b_q-sPnRD3kb0vQ';

  var listEl = document.getElementById('list');
  var badgeEl = document.getElementById('badge');

  // Load unseen count and fetch logs
  chrome.storage.local.get(['ssUnseenCount'], function(data) {
    badgeEl.textContent = data.ssUnseenCount || 0;
    fetchLogs();
  });

  // Mark all read
  document.getElementById('mark-read').addEventListener('click', function() {
    chrome.storage.local.set({ ssUnseenCount: 0 });
    badgeEl.textContent = '0';
  });

  // Refresh
  document.getElementById('refresh').addEventListener('click', fetchLogs);

  function fetchLogs() {
    var since = new Date(Date.now() - 72 * 3600 * 1000).toISOString();
    var url = API_URL + '/api/phantom-logs/?token=' + encodeURIComponent(API_TOKEN) + '&since=' + encodeURIComponent(since);

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
      detail.appendChild(document.createTextNode('\u0417\u0430\u043B\u043E\u0436\u0435\u043D\u0438: ' + log.param_diff + '  |  \u0420\u0435\u0430\u043B\u043D\u043E \u043D\u0430\u043B\u0438\u0447\u043D\u0438: ' + log.real_diff + '  |  '));
      var shadeSpan = document.createElement('span');
      shadeSpan.className = 'entry-shade';
      shadeSpan.textContent = '\u041B\u0438\u043F\u0441\u0432\u0430\u0449\u0438: ' + (log.shade > 0 ? '+' : '') + log.shade;
      detail.appendChild(shadeSpan);
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
