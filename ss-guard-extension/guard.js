/**
 * SoStocked Inventory Guard v2
 *
 * - Monitors work order edit pages, blocks overshipping
 * - Override button lets users proceed intentionally
 * - Polls backend for phantom quantity (shade) alerts
 * - Shows in-page toasts for new detections
 */

(function ssGuard() {
  'use strict';

  var GUARD_POLL_MS = 400;
  var SHADE_POLL_MS = 60000;
  var TOAST_DURATION_MS = 10000;
  var MAX_TOASTS = 5;

  // --- Guard state ---
  var currentViolations = [];
  var guardOverride = false;
  var overlay = null;

  function getOverlay() {
    if (overlay && document.body.contains(overlay)) return overlay;
    overlay = document.createElement('div');
    overlay.id = 'ss-guard-overlay';
    overlay.style.cssText = 'position:fixed;bottom:80px;left:50%;transform:translateX(-50%);z-index:99999;pointer-events:none;';
    document.body.appendChild(overlay);
    return overlay;
  }

  function showOverlay(count) {
    var ov = getOverlay();
    ov.textContent = '';
    var box = document.createElement('div');
    box.style.cssText = 'background:#fef2f2;border:2px solid #ef4444;border-radius:8px;padding:10px 20px;' +
      'font-size:14px;color:#991b1b;font-weight:600;box-shadow:0 4px 12px rgba(0,0,0,0.15);pointer-events:auto;' +
      'display:flex;align-items:center;gap:8px;';
    var icon = document.createElement('span');
    icon.style.fontSize = '20px';
    icon.textContent = '\u26A0';
    box.appendChild(icon);
    var msg = document.createElement('span');
    msg.textContent = count + (count === 1 ? ' \u043F\u0440\u043E\u0434\u0443\u043A\u0442' : ' \u043F\u0440\u043E\u0434\u0443\u043A\u0442\u0430') +
      ' \u0441 \u043F\u043E\u0432\u0435\u0447\u0435 \u0435\u0434\u0438\u043D\u0438\u0446\u0438 \u043E\u0442 \u043D\u0430\u043B\u0438\u0447\u043D\u0438\u0442\u0435. \u041A\u043E\u0440\u0438\u0433\u0438\u0440\u0430\u0439\u0442\u0435 \u043F\u0440\u0435\u0434\u0438 \u0437\u0430\u043F\u0438\u0441.';
    box.appendChild(msg);
    var overrideBtn = document.createElement('button');
    overrideBtn.className = 'ss-guard-override-btn';
    overrideBtn.textContent = '\u041F\u0440\u043E\u0434\u044A\u043B\u0436\u0438 \u0432\u044A\u043F\u0440\u0435\u043A\u0438 \u0442\u043E\u0432\u0430';
    overrideBtn.addEventListener('click', function() {
      guardOverride = true;
      hideOverlay();
      setTimeout(function() { guardOverride = false; }, 10000);
    });
    box.appendChild(overrideBtn);
    ov.appendChild(box);
  }

  function hideOverlay() {
    if (overlay && document.body.contains(overlay)) {
      overlay.textContent = '';
    }
  }

  function getSaveButton() {
    var buttons = document.querySelectorAll('button.btn.btn-success.btn-lg');
    for (var i = 0; i < buttons.length; i++) {
      if (buttons[i].textContent.trim().includes('Save')) return buttons[i];
    }
    return null;
  }

  function guardCheck() {
    if (!location.pathname.includes('/orders/') || (!location.pathname.includes('/edit/') && !location.pathname.includes('/add/'))) {
      hideOverlay();
      return;
    }

    var rows = document.querySelectorAll('.shipmen-logistics-table__row');
    if (!rows.length) return;

    var violations = [];

    for (var i = 0; i < rows.length; i++) {
      var row = rows[i];
      var invCell = row.querySelector('.shipmen-logistics-table__cell.width-120');
      if (!invCell) continue;
      var invSpan = invCell.querySelector('span.d-block');
      if (!invSpan) continue;
      var m = invSpan.textContent.match(/INV:\s*(\d+)/);
      if (!m) continue;
      var inv = parseInt(m[1], 10);

      var shippedCell = row.querySelector('.shipmen-logistics-table__cell.width-115');
      if (!shippedCell) continue;
      var input = shippedCell.querySelector('input.form-control');
      if (!input) continue;

      var shipped = parseInt(input.value, 10) || 0;

      if (shipped > inv) {
        shippedCell.classList.add('ss-guard-over');
        var badge = shippedCell.querySelector('.ss-guard-warning');
        if (!badge) {
          badge = document.createElement('span');
          badge.className = 'ss-guard-warning';
          shippedCell.appendChild(badge);
        }
        badge.textContent = shipped + ' > ' + inv + ' INV';
        violations.push({ shipped: shipped, inv: inv });
      } else {
        shippedCell.classList.remove('ss-guard-over');
        var b = shippedCell.querySelector('.ss-guard-warning');
        if (b) b.remove();
      }

      if (!input.dataset.ssGuard) {
        input.dataset.ssGuard = '1';
        input.addEventListener('input', guardCheck);
        input.addEventListener('change', guardCheck);
      }
    }

    currentViolations = violations;

    var saveBtn = getSaveButton();
    if (saveBtn && !saveBtn.dataset.ssGuardIntercept) {
      saveBtn.dataset.ssGuardIntercept = '1';
      saveBtn.addEventListener('click', function(e) {
        if (currentViolations.length > 0 && !guardOverride) {
          e.stopImmediatePropagation();
          e.preventDefault();
          showOverlay(currentViolations.length);
        }
        if (guardOverride) {
          guardOverride = false;
        }
      }, true);
    }

    if (violations.length > 0 && !guardOverride) {
      showOverlay(violations.length);
    } else {
      hideOverlay();
    }
  }

  // --- Shade alert toasts ---
  var toastContainer = null;

  function getToastContainer() {
    if (toastContainer && document.body.contains(toastContainer)) return toastContainer;
    toastContainer = document.createElement('div');
    toastContainer.id = 'ss-shade-toasts';
    toastContainer.style.cssText = 'position:fixed;top:20px;right:20px;z-index:99998;display:flex;flex-direction:column;gap:8px;max-width:380px;';
    document.body.appendChild(toastContainer);
    return toastContainer;
  }

  function showToast(log) {
    var container = getToastContainer();
    if (container.children.length >= MAX_TOASTS) return;

    var toast = document.createElement('div');
    toast.className = 'ss-shade-toast';

    var titleRow = document.createElement('div');
    titleRow.style.cssText = 'display:flex;justify-content:space-between;align-items:baseline;';
    var title = document.createElement('span');
    title.className = 'ss-shade-toast-title';
    title.textContent = '\u26A0 \u041B\u0438\u043F\u0441\u0432\u0430\u0449\u0438 \u0435\u0434\u0438\u043D\u0438\u0446\u0438';
    titleRow.appendChild(title);
    var paramVal = document.createElement('span');
    paramVal.style.cssText = 'font-size:16px;font-weight:800;color:#1e293b;';
    paramVal.textContent = (log.param_diff > 0 ? '+' : '') + log.param_diff;
    titleRow.appendChild(paramVal);
    toast.appendChild(titleRow);

    var line1 = document.createElement('div');
    line1.className = 'ss-shade-toast-line';
    line1.textContent = log.description;
    toast.appendChild(line1);

    var line2 = document.createElement('div');
    line2.className = 'ss-shade-toast-line';
    line2.textContent = '\u0420\u0435\u0430\u043B\u043D\u043E: ' + log.real_diff + ' | \u041B\u0438\u043F\u0441\u0432\u0430\u0449\u0438: ' + (log.shade > 0 ? '+' : '') + log.shade;
    toast.appendChild(line2);

    var timeEl = document.createElement('div');
    timeEl.className = 'ss-shade-toast-time';
    timeEl.textContent = relativeTime(log.created_at);
    toast.appendChild(timeEl);

    toast.addEventListener('click', function() { toast.remove(); });

    container.insertBefore(toast, container.firstChild);

    setTimeout(function() {
      if (toast.parentElement) toast.remove();
    }, TOAST_DURATION_MS);
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

  // --- Receive shade alerts from background worker (one tab only) ---
  chrome.runtime.onMessage.addListener(function(msg) {
    if (msg.type === 'shade-alerts' && msg.logs) {
      msg.logs.forEach(function(log) { showToast(log); });
    }
  });

  // --- Init ---
  setInterval(guardCheck, GUARD_POLL_MS);
  guardCheck();
})();
