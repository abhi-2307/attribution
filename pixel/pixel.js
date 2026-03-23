/**
 * First-Party Attribution Pixel
 * Tracks user events, captures UTM params and click IDs,
 * builds sessions, and sends data to the attribution backend.
 *
 * Auto-detects Shopify events — no manual integration needed.
 */

(function () {
  'use strict';

  const ENDPOINT = '{{PIXEL_BASE_URL}}/v1/pixel/event';
  const CLIENT_ID = '{{CLIENT_ID}}';
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

  function hashEmail(email) {
    // Simple SHA-256 via SubtleCrypto — async, best effort
    if (!email || !crypto.subtle) return Promise.resolve(null);
    var encoded = new TextEncoder().encode(email.trim().toLowerCase());
    return crypto.subtle.digest('SHA-256', encoded).then(function (buf) {
      return Array.from(new Uint8Array(buf)).map(function (b) {
        return b.toString(16).padStart(2, '0');
      }).join('');
    }).catch(function () { return null; });
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
          parsed.last_active = now;
          setCookie(SESSION_COOKIE, JSON.stringify(parsed), 1);
          return parsed.sid;
        }
      } catch (e) {}
    }

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
      client_id: CLIENT_ID,
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

    if (navigator.sendBeacon) {
      var blob = new Blob([body], { type: 'application/json' });
      var sent = navigator.sendBeacon(ENDPOINT, blob);
      if (sent) return;
    }

    fetch(ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body,
      keepalive: true,
    }).catch(function () {});
  }

  // ─── Public API ───────────────────────────────────────────────────────────

  var Pixel = {
    pageView: function () {
      sendEvent(buildPayload('page_view'));
    },
    productView: function (data) {
      sendEvent(buildPayload('product_view', data || {}));
    },
    addToCart: function (data) {
      sendEvent(buildPayload('add_to_cart', data || {}));
    },
    checkoutStart: function (data) {
      sendEvent(buildPayload('checkout_start', data || {}));
    },
    purchase: function (data) {
      sendEvent(buildPayload('purchase', data || {}));
    },
    track: function (eventName, data) {
      sendEvent(buildPayload(eventName, data || {}));
    },
  };

  // ─── Shopify Auto-Detection ───────────────────────────────────────────────

  function shopifyAutoTrack() {
    var path = window.location.pathname;
    var meta = (window.ShopifyAnalytics && window.ShopifyAnalytics.meta) || {};
    var pageType = (meta.page && meta.page.pageType) || '';

    // ── Product view ──────────────────────────────────────────────────────
    if (pageType === 'product' || (meta.product && meta.product.id)) {
      var product = meta.product || {};
      Pixel.productView({
        product_id: String(product.id || ''),
        variant_id: String(product.selectedVariantId || ''),
        price: product.price ? product.price / 100 : null,
      });
    }

    // ── Collection view ───────────────────────────────────────────────────
    if (pageType === 'collection') {
      sendEvent(buildPayload('collection_view', {
        collection: (meta.page && meta.page.handle) || null,
      }));
    }

    // ── Search ────────────────────────────────────────────────────────────
    if (pageType === 'search' || path.indexOf('/search') === 0) {
      sendEvent(buildPayload('search', {
        search_query: getUrlParam('q'),
      }));
    }

    // ── Cart view ─────────────────────────────────────────────────────────
    if (path === '/cart') {
      sendEvent(buildPayload('cart_view'));
    }

    // ── Checkout start ────────────────────────────────────────────────────
    if (path.indexOf('/checkouts/') !== -1 && path.indexOf('thank_you') === -1) {
      Pixel.checkoutStart({});
    }

    // ── Purchase (thank you page) ─────────────────────────────────────────
    if (path.indexOf('thank_you') !== -1 || path.indexOf('/orders/') !== -1) {
      var checkout = window.Shopify && window.Shopify.checkout;
      if (checkout) {
        var purchaseData = {
          order_id: String(checkout.order_id || checkout.id || ''),
          order_value: parseFloat(checkout.total_price || 0),
          currency: checkout.currency || null,
        };
        var email = checkout.email || '';
        if (email) {
          hashEmail(email).then(function (hash) {
            purchaseData.email_hash = hash;
            Pixel.purchase(purchaseData);
          });
        } else {
          Pixel.purchase(purchaseData);
        }
      } else {
        // Fallback — fire purchase without order details
        Pixel.purchase({});
      }
    }

    // ── Add to cart — intercept fetch + XHR to /cart/add.js ──────────────
    interceptCartAdd();
  }

  function interceptCartAdd() {
    // Intercept fetch
    var originalFetch = window.fetch;
    window.fetch = function (input, init) {
      var url = typeof input === 'string' ? input : (input && input.url) || '';
      if (url.indexOf('/cart/add') !== -1) {
        var body = (init && init.body) || null;
        try {
          var data = typeof body === 'string' ? JSON.parse(body) : {};
          Pixel.addToCart({
            product_id: String(data.id || data.items && data.items[0] && data.items[0].id || ''),
            variant_id: String(data.id || ''),
            quantity: data.quantity || (data.items && data.items[0] && data.items[0].quantity) || 1,
          });
        } catch (e) {}
      }
      return originalFetch.apply(this, arguments);
    };

    // Intercept XMLHttpRequest
    var originalOpen = XMLHttpRequest.prototype.open;
    var originalSend = XMLHttpRequest.prototype.send;

    XMLHttpRequest.prototype.open = function (method, url) {
      this._pxUrl = url || '';
      return originalOpen.apply(this, arguments);
    };

    XMLHttpRequest.prototype.send = function (body) {
      if (this._pxUrl && this._pxUrl.indexOf('/cart/add') !== -1) {
        try {
          var data = typeof body === 'string' ? JSON.parse(body) : {};
          Pixel.addToCart({
            product_id: String(data.id || ''),
            variant_id: String(data.id || ''),
            quantity: data.quantity || 1,
          });
        } catch (e) {}
      }
      return originalSend.apply(this, arguments);
    };

    // Also intercept form submissions to /cart/add
    document.addEventListener('submit', function (e) {
      var form = e.target;
      if (form && form.action && form.action.indexOf('/cart/add') !== -1) {
        var variantInput = form.querySelector('[name="id"]');
        var quantityInput = form.querySelector('[name="quantity"]');
        Pixel.addToCart({
          variant_id: variantInput ? variantInput.value : '',
          quantity: quantityInput ? parseInt(quantityInput.value) || 1 : 1,
        });
      }
    }, true);
  }

  // ─── First Visit & Session Start ─────────────────────────────────────────

  function trackFirstVisitAndSession() {
    var isFirstVisit = !getCookie(VISITOR_COOKIE);
    var isNewSession = !getCookie(SESSION_COOKIE);

    // getOrCreateVisitorId/SessionId will create cookies if missing
    getOrCreateVisitorId();
    getOrCreateSessionId();

    if (isFirstVisit) {
      sendEvent(buildPayload('first_visit'));
    }
    if (isNewSession || isFirstVisit) {
      sendEvent(buildPayload('session_start'));
    }
  }

  // ─── User Engagement Duration ─────────────────────────────────────────────

  function trackEngagement() {
    var startTime = Date.now();
    var sent = false;

    function sendEngagement() {
      if (sent) return;
      sent = true;
      var duration = Math.round((Date.now() - startTime) / 1000);
      if (duration < 1) return;
      sendEvent(buildPayload('user_engagement', { engagement_time_sec: duration }));
    }

    // Fire on page hide (tab switch, close, navigate away)
    document.addEventListener('visibilitychange', function () {
      if (document.visibilityState === 'hidden') sendEngagement();
    });

    // Fallback for older browsers
    window.addEventListener('beforeunload', sendEngagement);
  }

  // ─── Auto-init ────────────────────────────────────────────────────────────

  captureAttributionParams();

  function init() {
    trackFirstVisitAndSession();
    Pixel.pageView();
    shopifyAutoTrack();
    trackEngagement();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  window.Pixel = Pixel;
})();
