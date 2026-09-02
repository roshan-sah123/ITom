/**
 * ITOM Portal & Operations Analytics - Utility Helpers
 * 
 * Provides DOM sanitization (XSS prevention), debouncing, numerical formatting,
 * storage arithmetic, and table helper utilities with zero-build browser compatibility.
 */

(function (root, factory) {
  if (typeof define === 'function' && define.amd) {
    define([], factory);
  } else if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    const exports = factory();
    root.ITOM_UTILS = exports;
    Object.assign(root, exports);
  }
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  /**
   * Strictly sanitize any untrusted string prior to DOM injection.
   * Prevents Cross-Site Scripting (XSS) across user, device, serial, and telemetry values.
   * 
   * @param {any} str
   * @returns {string}
   */
  function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  /**
   * Debounce higher-order function to delay execution until delay ms of idle time.
   * 
   * @param {Function} func
   * @param {number} delay
   * @returns {Function}
   */
  function debounce(func, delay = 200) {
    let timeoutId;
    return function (...args) {
      clearTimeout(timeoutId);
      timeoutId = setTimeout(() => func.apply(this, args), delay);
    };
  }

  /**
   * Format numbers with localized commas (e.g., 25987 -> "25,987").
   * 
   * @param {number|string} val
   * @returns {string}
   */
  function formatNumber(val) {
    const num = Number(val);
    if (isNaN(num)) return '0';
    return num.toLocaleString();
  }

  /**
   * Format raw byte counts into human-readable strings (e.g. GB / TB).
   * 
   * @param {number} bytes
   * @param {number} decimals
   * @returns {string}
   */
  function formatBytes(bytes, decimals = 2) {
    const num = Number(bytes);
    if (isNaN(num) || num <= 0) return '0 B';
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
    const i = Math.floor(Math.log(num) / Math.log(k));
    return parseFloat((num / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
  }

  /**
   * Convert byte value to GB number with specified decimal precision.
   * 
   * @param {number} bytes
   * @param {number} decimals
   * @returns {number}
   */
  function bytesToGB(bytes, decimals = 1) {
    const num = Number(bytes);
    if (isNaN(num) || num <= 0) return 0;
    const gb = num / (1024 * 1024 * 1024);
    return parseFloat(gb.toFixed(decimals));
  }

  /**
   * Format ISO date strings into localized datetime strings.
   * 
   * @param {string} dateStr
   * @returns {string}
   */
  function formatDate(dateStr) {
    if (!dateStr || dateStr === 'N/A') return 'N/A';
    try {
      const d = new Date(dateStr);
      if (isNaN(d.getTime())) return String(dateStr);
      return d.toLocaleDateString(undefined, {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      });
    } catch {
      return String(dateStr);
    }
  }

  /**
   * Safely reset scrolling for table container.
   * 
   * @param {string|HTMLElement} target
   */
  function resetTableScroll(target) {
    const elem = typeof target === 'string' ? document.getElementById(target) : target;
    if (elem) {
      elem.scrollTop = 0;
      elem.scrollLeft = 0;
    }
  }

  return {
    escapeHtml,
    debounce,
    formatNumber,
    formatBytes,
    bytesToGB,
    formatDate,
    resetTableScroll,
  };
});
