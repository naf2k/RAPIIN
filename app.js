/* BERESIN - shared frontend helpers (auth, API fetch, routing). */
(function () {
  "use strict";

  var API_BASE = "/api";
  var TOKEN_KEY = "beresin_token";
  var USER_KEY = "beresin_user";

  function getToken() {
    return localStorage.getItem(TOKEN_KEY) || "";
  }

  function getUser() {
    try {
      return JSON.parse(localStorage.getItem(USER_KEY) || "null");
    } catch (e) {
      return null;
    }
  }

  function setSession(token, user) {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    if (user) localStorage.setItem(USER_KEY, JSON.stringify(user));
  }

  function clearSession() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  }

  function isLoggedIn() {
    return !!getToken();
  }

  function userRole() {
    var u = getUser();
    return u ? u.role : null;
  }

  function redirectToLogin() {
    clearSession();
    window.location.href = "/login.html";
  }

  function redirectByRole(role) {
    if (role === "SUPERVISOR") {
      window.location.href = "/supervisor/overview.html";
    } else {
      window.location.href = "/index.html";
    }
  }

  function logout() {
    var token = getToken();
    clearSession();
    if (token) {
      fetch(API_BASE + "/auth/logout", {
        method: "POST",
        headers: { Authorization: "Bearer " + token },
      }).catch(function () {});
    }
    window.location.href = "/login.html";
  }

  async function api(method, path, body) {
    var headers = { "Content-Type": "application/json" };
    var token = getToken();
    if (token) headers.Authorization = "Bearer " + token;

    var opts = { method: method, headers: headers };
    if (body !== undefined && body !== null) {
      opts.body = JSON.stringify(body);
    }

    var resp;
    try {
      resp = await fetch(API_BASE + path, opts);
    } catch (err) {
      throw new Error("Tidak dapat terhubung ke server. Periksa koneksi Anda.");
    }

    if (resp.status === 401) {
      // Token expired/invalid.
      if (!window.location.pathname.endsWith("/login.html")) {
        redirectToLogin();
      }
      throw new Error("Sesi berakhir. Silakan masuk kembali.");
    }

    var data = null;
    try {
      data = await resp.json();
    } catch (e) {
      data = {};
    }

    if (!resp.ok) {
      var detail = data && data.detail;
      var msg = typeof detail === "string" ? detail : "Terjadi kesalahan. Silakan coba lagi.";
      throw new Error(msg);
    }
    return data;
  }

  function el(id) {
    return document.getElementById(id);
  }

  function esc(str) {
    if (str === null || str === undefined) return "";
    var div = document.createElement("div");
    div.textContent = String(str);
    return div.innerHTML;
  }

  function showToast(message, type) {
    var container = document.querySelector(".toast-container");
    if (!container) {
      container = document.createElement("div");
      container.className = "toast-container";
      document.body.appendChild(container);
    }
    var toast = document.createElement("div");
    toast.className = "toast toast--" + (type || "info");
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(function () {
      toast.classList.add("toast--visible");
    }, 10);
    setTimeout(function () {
      toast.classList.remove("toast--visible");
      setTimeout(function () { toast.remove(); }, 300);
    }, 4000);
  }

  function showError(message) {
    showToast(message, "error");
  }

  function initNotifications() {
    var bell = document.getElementById("notification-bell");
    if (!bell) return;
    var role = userRole();
    var basePath = role === "SUPERVISOR" ? "/supervisor" : "/user";

    var badge = bell.querySelector(".notif-badge");
    var panel = document.getElementById("notification-panel");
    var listEl = document.getElementById("notification-list");
    if (!panel || !listEl) return;

    async function refresh() {
      try {
        var data = await api("GET", basePath + "/notifications");
        var items = data.items || data;
        var unread = data.unread !== undefined ? data.unread : items.filter(function (n) { return !n.is_read; }).length;
        if (badge) {
          badge.textContent = unread > 0 ? (unread > 9 ? "9+" : String(unread)) : "";
          badge.hidden = unread === 0;
        }
        listEl.innerHTML = "";
        if (!items.length) {
          var empty = document.createElement("p");
          empty.className = "history-empty";
          empty.textContent = "Belum ada notifikasi.";
          listEl.appendChild(empty);
          return;
        }
        items.forEach(function (n) {
          var item = document.createElement("a");
          item.className = "notif-item" + (n.is_read ? "" : " notif-item--unread");
          item.href = "#";
          var t = document.createElement("strong");
          t.textContent = n.title;
          var b = document.createElement("span");
          b.textContent = n.body || "";
          item.appendChild(t);
          item.appendChild(b);
          item.addEventListener("click", function (e) {
            e.preventDefault();
            if (!n.is_read) {
              api("POST", basePath + "/notifications/" + n.id + "/read").catch(function () {});
              item.classList.remove("notif-item--unread");
              refresh();
            }
          });
          listEl.appendChild(item);
        });
      } catch (e) { /* silent */ }
    }

    bell.addEventListener("click", function (e) {
      e.stopPropagation();
      var hidden = panel.hidden;
      panel.hidden = !hidden;
      if (panel.hidden === false) refresh();
    });
    document.addEventListener("click", function (e) {
      if (!bell.contains(e.target) && !panel.contains(e.target)) panel.hidden = true;
    });

    // Poll for new notifications every 15 seconds.
    refresh();
    setInterval(refresh, 15000);
  }

  var ICON_MENU = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M4 6h16"/><path d="M4 12h16"/><path d="M4 18h16"/></svg>';
  var ICON_CLOSE = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>';

  // The sidebar rests as an icon rail on desktop and becomes a sheet behind a
  // hamburger on small screens. The toggle and scrim are built here so every
  // page that already renders .sidebar gains the behaviour without new markup.
  function initSidebarDrawer() {
    var sidebar = document.querySelector(".sidebar");
    if (!sidebar) return;

    var toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "sidebar-toggle";
    toggle.setAttribute("aria-label", "Buka navigasi");
    toggle.setAttribute("aria-expanded", "false");
    toggle.setAttribute("aria-controls", "beresin-sidebar");
    toggle.innerHTML = ICON_MENU;
    if (!sidebar.id) sidebar.id = "beresin-sidebar";

    var topbar = document.querySelector(".topbar");
    var brand = topbar && topbar.querySelector(".mobile-brand");
    if (topbar && brand) topbar.insertBefore(toggle, brand);
    else if (topbar) topbar.insertBefore(toggle, topbar.firstChild);
    else document.body.insertBefore(toggle, document.body.firstChild);

    var scrim = document.createElement("div");
    scrim.className = "sidebar-scrim";
    scrim.hidden = true;
    document.body.appendChild(scrim);

    var close = document.createElement("button");
    close.type = "button";
    close.className = "sidebar-close";
    close.setAttribute("aria-label", "Tutup navigasi");
    close.innerHTML = ICON_CLOSE;
    var head = document.createElement("div");
    head.className = "sidebar-drawer-head";
    head.appendChild(close);
    sidebar.insertBefore(head, sidebar.firstChild);

    var lastFocused = null;

    function openDrawer() {
      lastFocused = document.activeElement;
      document.body.classList.add("sidebar-drawer-open");
      scrim.hidden = false;
      toggle.setAttribute("aria-expanded", "true");
      close.focus();
    }

    function closeDrawer() {
      document.body.classList.remove("sidebar-drawer-open");
      scrim.hidden = true;
      toggle.setAttribute("aria-expanded", "false");
      if (lastFocused && typeof lastFocused.focus === "function") lastFocused.focus();
    }

    toggle.addEventListener("click", function () {
      if (document.body.classList.contains("sidebar-drawer-open")) closeDrawer();
      else openDrawer();
    });
    close.addEventListener("click", closeDrawer);
    scrim.addEventListener("click", closeDrawer);
    sidebar.addEventListener("click", function (event) {
      if (event.target.closest("a") && document.body.classList.contains("sidebar-drawer-open")) closeDrawer();
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && document.body.classList.contains("sidebar-drawer-open")) closeDrawer();
    });
  }

  function initLogoutButtons() {
    document.querySelectorAll("[data-logout]").forEach(function (btn) {
      btn.addEventListener("click", function (e) {
        e.preventDefault();
        logout();
      });
    });
  }

  // Guard: pages marked with data-require-role enforce RBAC on the client.
  function initAuthGuard() {
    var body = document.body;
    var required = body.getAttribute("data-require-role");
    if (!required) return;

    if (!isLoggedIn()) {
      redirectToLogin();
      return;
    }
    var role = userRole();
    if (required !== role) {
      redirectByRole(role || "USER");
    }
  }

  window.BERESIN = {
    getToken: getToken,
    getUser: getUser,
    setSession: setSession,
    clearSession: clearSession,
    isLoggedIn: isLoggedIn,
    userRole: userRole,
    redirectToLogin: redirectToLogin,
    redirectByRole: redirectByRole,
    logout: logout,
    api: api,
    el: el,
    esc: esc,
    showToast: showToast,
    showError: showError,
    initLogoutButtons: initLogoutButtons,
    initAuthGuard: initAuthGuard,
    initNotifications: initNotifications,
    initSidebarDrawer: initSidebarDrawer,
  };

  document.addEventListener("DOMContentLoaded", function () {
    window.BERESIN.initSidebarDrawer();
    window.BERESIN.initLogoutButtons();
    window.BERESIN.initAuthGuard();
    window.BERESIN.initNotifications();
  });
})();
