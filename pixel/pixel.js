/**
 * First-Party Attribution Pixel
 * Tracks user events, captures UTM params and click IDs,
 * builds sessions, and sends data to the attribution backend.
 */

(function () {
  'use strict';

  const ENDPOINT = '{{PIXEL_BASE_URL}}/v1/pixel/event';
  const VISITOR_COOKIE = '_px_vid';
  const SESSION_COOKIE = '_px_sid';
  const ATTR_STORAGE_KEY = '_px_attr';
  const SESSION_TIMEOUT_MS = 30 * 60 * 1000; // 30 minutes
  const VISITOR_EXPIRY_DAYS = 365;

  // ─── Utilities ────────────────────────────────────────────────────────────

  function uuidv4() {
    if (crypto && crypto.randomUUID) return crypto.randomUUID();
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
      var r = (Math.random() * 16) | 0,
        v = c === 'x' ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  }

  function getCookie(name) {
    var match = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'));
    return match ? decodeURIComponent(match[1]) : null;
  }

  function setCookie(name, value, days) {
    var expires = new Date(Date.now() + days * 864e5).toUTCString();
    document.cookie =
      name + '=' + encodeURIComponent(value) + '; expires=' + expires + '; path=/; SameSite=Lax';
  }

  function getUrlParam(name) {
    var params = new URLSearchParams(window.location.search);
    return params.get(name) || null;
  }

  // ─── Visitor ID ───────────────────────────────────────────────────────────

  function getOrCreateVisitorId() {
    var vid = getCookie(VISITOR_COOKIE);
    if (!vid) {
      vid = uuidv4();
      setCookie(VISITOR_COOKIE, vid, VISITOR_EXPIRY_DAYS);
    }
    return vid;
  }

  // ─── Session ID ───────────────────────────────────────────────────────────

  function getOrCreateSessionId() {
    var cookieVal = getCookie(SESSION_COOKIE);
    var now = Date.now();

    if (cookieVal) {
      try {
        var parsed = JSON.parse(decodeURIComponent(cookieVal));
        if (now - parsed.last_active < SESSION_TIMEOUT_MS) {
          // Refresh last_active
          parsed.last_active = now;
          setCookie(SESSION_COOKIE, JSON.stringify(parsed), 1);
          return parsed.sid;
        }
      } catch (e) {}
    }

    // New session
    var newSession = { sid: uuidv4(), last_active: now };
    setCookie(SESSION_COOKIE, JSON.stringify(newSession), 1);
    return newSession.sid;
  }

  // ─── Attribution Parameters ───────────────────────────────────────────────

  var UTM_PARAMS = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term'];
  var CLICK_IDS = ['fbclid', 'gclid', 'ttclid', 'msclkid'];
  var ALL_ATTR_PARAMS = UTM_PARAMS.concat(CLICK_IDS);

  function captureAttributionParams() {
    var incoming = {};
    ALL_ATTR_PARAMS.forEach(function (key) {
      var val = getUrlParam(key);
      if (val) incoming[key] = val;
    });

    if (Object.keys(incoming).length === 0) return;

    // Merge with existing stored attribution — incoming wins
    var existing = {};
    try {
      existing = JSON.parse(localStorage.getItem(ATTR_STORAGE_KEY) || '{}');
    } catch (e) {}

    var merged = Object.assign({}, existing, incoming);
    localStorage.setItem(ATTR_STORAGE_KEY, JSON.stringify(merged));
  }

  function getStoredAttribution() {
    try {
      return JSON.parse(localStorage.getItem(ATTR_STORAGE_KEY) || '{}');
    } catch (e) {
      return {};
    }
  }

  // ─── Event Sending ────────────────────────────────────────────────────────

  function buildPayload(eventName, extraData) {
    var attr = getStoredAttribution();

    var payload = {
      event_id: uuidv4(),
      event_name: eventName,
      visitor_id: getOrCreateVisitorId(),
      session_id: getOrCreateSessionId(),
      url: window.location.href,
      path: window.location.pathname,
      referrer: document.referrer || null,
      utm_source: attr.utm_source || null,
      utm_medium: attr.utm_medium || null,
      utm_campaign: attr.utm_campaign || null,
      utm_content: attr.utm_content || null,
      utm_term: attr.utm_term || null,
      fbclid: attr.fbclid || null,
      gclid: attr.gclid || null,
      ttclid: attr.ttclid || null,
      msclkid: attr.msclkid || null,
      user_agent: navigator.userAgent,
      timestamp: Math.floor(Date.now() / 1000),
    };

    if (extraData) Object.assign(payload, extraData);
    return payload;
  }

  function sendEvent(payload) {
    var body = JSON.stringify(payload);

    // Primary: sendBeacon (non-blocking, survives page unload)
    if (navigator.sendBeacon) {
      var blob = new Blob([body], { type: 'application/json' });
      var sent = navigator.sendBeacon(ENDPOINT, blob);
      if (sent) return;
    }

    // Fallback: fetch
    fetch(ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body,
      keepalive: true,
    }).catch(function () {});
  }

  // ─── Public API ───────────────────────────────────────────────────────────

  var Pixel = {
    /**
     * Track a page view. Called automatically on load.
     */
    pageView: function () {
      var payload = buildPayload('page_view');
      sendEvent(payload);
    },

    /**
     * Track a product view.
     * @param {Object} data - { product_id, product_name, price }
     */
    productView: function (data) {
      var payload = buildPayload('product_view', data || {});
      sendEvent(payload);
    },

    /**
     * Track add to cart.
     * @param {Object} data - { product_id, variant_id, quantity, price }
     */
    addToCart: function (data) {
      var payload = buildPayload('add_to_cart', data || {});
      sendEvent(payload);
    },

    /**
     * Track checkout start.
     * @param {Object} data - { cart_value, item_count }
     */
    checkoutStart: function (data) {
      var payload = buildPayload('checkout_start', data || {});
      sendEvent(payload);
    },

    /**
     * Track a purchase / conversion.
     * @param {Object} data - { order_id, order_value, currency, email_hash }
     */
    purchase: function (data) {
      var payload = buildPayload('purchase', data || {});
      sendEvent(payload);
    },

    /**
     * Generic custom event.
     * @param {string} eventName
     * @param {Object} data
     */
    track: function (eventName, data) {
      var payload = buildPayload(eventName, data || {});
      sendEvent(payload);
    },
  };

  // ─── Auto-init ────────────────────────────────────────────────────────────

  // 1. Capture/refresh attribution params from URL on every page load
  captureAttributionParams();

  // 2. Fire automatic page_view
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () {
      Pixel.pageView();
    });
  } else {
    Pixel.pageView();
  }

  // 3. Expose globally
  window.Pixel = Pixel;
})();
