(function() {
  'use strict';

  var API_URL = 'https://srv1563194.hstgr.cloud:4443';
  var API_TOKEN = 'Xg5ci39x_pIQXQzSHPkZtmbpZvL0b_q-sPnRD3kb0vQ';

  var listEl = document.getElementById('list');
  var badgeEl = document.getElementById('badge');

  // Auto-mark as read on popup open, then fetch
  chrome.storage.local.set({ ssUnseenCount: 0 });
  badgeEl.textContent = '0';
  fetchLogs();

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

      var top = document.createElement('div');
      top.className = 'entry-top';
      var asin = document.createElement('span');
      asin.className = 'entry-asin';
      asin.textContent = log.asin;
      var shipment = document.createElement('span');
      shipment.className = 'shipment';
      shipment.textContent = '  #' + log.shipment_id;
      asin.appendChild(shipment);
      top.appendChild(asin);
      var paramVal = document.createElement('span');
      paramVal.className = 'entry-param';
      paramVal.textContent = (log.param_diff > 0 ? '+' : '') + log.param_diff;
      top.appendChild(paramVal);
      entry.appendChild(top);

      var desc = document.createElement('div');
      desc.className = 'entry-desc';
      desc.textContent = log.description;
      entry.appendChild(desc);

      var bottom = document.createElement('div');
      bottom.className = 'entry-bottom';
      var nums = document.createElement('span');
      nums.className = 'entry-nums';
      nums.textContent = '\u0420\u0435\u0430\u043B\u043D\u043E: ' + log.real_diff + '  \u00B7  ';
      var shadeSpan = document.createElement('span');
      shadeSpan.className = 'entry-shade';
      shadeSpan.textContent = '\u041B\u0438\u043F\u0441\u0432\u0430\u0449\u0438: ' + (log.shade > 0 ? '+' : '') + log.shade;
      nums.appendChild(shadeSpan);
      bottom.appendChild(nums);
      var meta = document.createElement('span');
      meta.className = 'entry-meta';
      meta.textContent = log.user + ' \u00B7 ' + relativeTime(log.created_at);
      bottom.appendChild(meta);
      entry.appendChild(bottom);

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
