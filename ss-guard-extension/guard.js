/**
 * SoStocked Inventory Guard
 *
 * Monitors work order edit pages. For each product row, compares the Shipped
 * input value against the INV (inventory) counter. If shipped > inventory,
 * the input is highlighted red and the Save & Preview button is blocked.
 *
 * Approach: Uses a persistent overlay div (outside the Vue app tree) for
 * warnings, CSS classes for input highlighting, and click interception
 * on the Save button. This survives Vue re-renders.
 */

(function ssGuard() {
  'use strict';

  const POLL_MS = 400;

  // Persistent overlay container — lives outside the Vue app tree
  let overlay = null;
  function getOverlay() {
    if (overlay && document.body.contains(overlay)) return overlay;
    overlay = document.createElement('div');
    overlay.id = 'ss-guard-overlay';
    overlay.style.cssText = 'position:fixed;bottom:80px;left:50%;transform:translateX(-50%);z-index:99999;pointer-events:none;';
    document.body.appendChild(overlay);
    return overlay;
  }

  // Track violations state
  let currentViolations = [];

  function check() {
    // Only run on work order / purchase order edit pages
    if (!location.pathname.includes('/orders/') || !location.pathname.includes('/edit/')) {
      hideOverlay();
      return;
    }

    const rows = document.querySelectorAll('.shipmen-logistics-table__row');
    if (!rows.length) return;

    const violations = [];

    for (const row of rows) {
      // Parse INV value
      const invCell = row.querySelector('.shipmen-logistics-table__cell.width-120');
      if (!invCell) continue;
      const invSpan = invCell.querySelector('span.d-block');
      if (!invSpan) continue;
      const invMatch = invSpan.textContent.match(/INV:\s*(\d+)/);
      if (!invMatch) continue;
      const inv = parseInt(invMatch[1], 10);

      // Get Shipped input
      const shippedCell = row.querySelector('.shipmen-logistics-table__cell.width-115');
      if (!shippedCell) continue;
      const input = shippedCell.querySelector('input.form-control');
      if (!input) continue;

      const shipped = parseInt(input.value, 10) || 0;

      if (shipped > inv) {
        // Highlight input red via CSS class on the cell
        shippedCell.classList.add('ss-guard-over');

        // Add or update warning badge
        let badge = shippedCell.querySelector('.ss-guard-warning');
        if (!badge) {
          badge = document.createElement('span');
          badge.className = 'ss-guard-warning';
          shippedCell.appendChild(badge);
        }
        badge.textContent = shipped + ' > ' + inv + ' INV';

        violations.push({ shipped, inv });
      } else {
        shippedCell.classList.remove('ss-guard-over');
        const badge = shippedCell.querySelector('.ss-guard-warning');
        if (badge) badge.remove();
      }

      // Bind input listeners (re-bind every poll since Vue replaces DOM nodes)
      if (!input.dataset.ssGuard) {
        input.dataset.ssGuard = '1';
        input.addEventListener('input', check);
        input.addEventListener('change', check);
      }
    }

    currentViolations = violations;

    // Handle Save button — use click interception instead of CSS pointer-events
    const saveBtn = getSaveButton();
    if (saveBtn && !saveBtn.dataset.ssGuardIntercept) {
      saveBtn.dataset.ssGuardIntercept = '1';
      saveBtn.addEventListener('click', function(e) {
        if (currentViolations.length > 0) {
          e.stopImmediatePropagation();
          e.preventDefault();
          showOverlay(currentViolations.length);
        }
      }, true); // capture phase — fires before the app's handler
    }

    // Update visual state
    if (violations.length > 0) {
      if (saveBtn) saveBtn.classList.add('ss-guard-blocked');
      showOverlay(violations.length);
    } else {
      if (saveBtn) saveBtn.classList.remove('ss-guard-blocked');
      hideOverlay();
    }
  }

  function getSaveButton() {
    const buttons = document.querySelectorAll('button.btn.btn-success.btn-lg');
    for (const btn of buttons) {
      if (btn.textContent.trim().includes('Save')) return btn;
    }
    return null;
  }

  function showOverlay(count) {
    var ov = getOverlay();
    // Build overlay content safely with DOM methods
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
    msg.textContent = count + (count === 1 ? ' product' : ' products') +
      ' shipping more units than available inventory. Fix before saving.';
    box.appendChild(msg);
    ov.appendChild(box);
  }

  function hideOverlay() {
    if (overlay && document.body.contains(overlay)) {
      overlay.textContent = '';
    }
  }

  // Poll — resilient to Vue re-renders since we re-query the DOM every time
  setInterval(check, POLL_MS);

  // Initial check
  check();
})();
